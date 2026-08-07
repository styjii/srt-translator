"""
translate_srt.py — Module de traduction de sous-titres .srt (orienté classes)
--------------------------------------------------------------------------------
Ce fichier ne contient AUCUN code d'interface (pas de CLI, pas de print
destinés à l'utilisateur). Il expose des classes réutilisables :

    SrtDocument        — parse / réécrit un fichier .srt
    TranslationEngine  — classe abstraite pour un moteur de traduction
    DeepLEngine         — implémentation DeepL
    AnthropicEngine     — implémentation Anthropic (Claude)
    SubtitleTranslator  — orchestre document + moteur

Pour l'interface en ligne de commande, voir app.py (Typer + Rich).

Exemple d'utilisation :

    from translate_srt import SrtDocument, DeepLEngine, SubtitleTranslator

    doc = SrtDocument.from_file("input.srt")
    engine = DeepLEngine(source="EN", target="FR")
    translator = SubtitleTranslator(engine)

    def on_progress(done, total):
        print(f"{done}/{total}")

    translator.translate(doc, progress_cb=on_progress)
    doc.write("output_fr.srt")
"""

from __future__ import annotations

import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Erreurs dédiées (utile pour un affichage propre côté CLI)
# ---------------------------------------------------------------------------
class MissingApiKeyError(RuntimeError):
    pass


class TranslationEngineError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Modèle de données
# ---------------------------------------------------------------------------
@dataclass
class SubtitleBlock:
    index: str
    timing: str
    text: str


# ---------------------------------------------------------------------------
# Document SRT : parsing, accès aux blocs, écriture
# ---------------------------------------------------------------------------
class SrtDocument:
    """
    Représente un fichier .srt chargé en mémoire.

    Le parsing se fait ligne par ligne (O(n)), volontairement sans regex sur
    l'ensemble du fichier, pour ne jamais risquer un backtracking
    catastrophique sur de gros fichiers ou des formats irréguliers.
    """

    _TIMING_LINE_RE = re.compile(
        r"^\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}"
    )
    _INDEX_LINE_RE = re.compile(r"^\s*\d+\s*$")

    def __init__(self, blocks: List[SubtitleBlock], source_path: Optional[str] = None):
        self.blocks = blocks
        self.source_path = source_path

    def __len__(self) -> int:
        return len(self.blocks)

    def __iter__(self):
        return iter(self.blocks)

    @property
    def texts(self) -> List[str]:
        """Liste des textes originaux, dans l'ordre des blocs."""
        return [b.text for b in self.blocks]

    def apply_translations(self, translated_texts: List[str]) -> None:
        """Remplace le texte de chaque bloc par sa traduction (même ordre)."""
        if len(translated_texts) != len(self.blocks):
            raise TranslationEngineError(
                f"{len(self.blocks)} répliques attendues, {len(translated_texts)} reçues."
            )
        for block, new_text in zip(self.blocks, translated_texts):
            block.text = new_text

    @classmethod
    def from_file(cls, path: str) -> "SrtDocument":
        with open(path, "r", encoding="utf-8-sig") as f:
            raw_lines = f.read().replace("\r\n", "\n").replace("\r", "\n").split("\n")

        blocks: List[SubtitleBlock] = []
        i = 0
        n = len(raw_lines)

        while i < n:
            line = raw_lines[i].strip()
            if not line:
                i += 1
                continue
            if not cls._INDEX_LINE_RE.match(line):
                i += 1
                continue

            index = line
            i += 1
            if i >= n:
                break

            timing_line = raw_lines[i].strip()
            if not cls._TIMING_LINE_RE.match(timing_line):
                continue

            i += 1
            text_lines = []
            while (
                i < n
                and raw_lines[i].strip() != ""
                and not cls._INDEX_LINE_RE.match(raw_lines[i].strip())
            ):
                text_lines.append(raw_lines[i].rstrip())
                i += 1

            blocks.append(
                SubtitleBlock(index=index, timing=timing_line, text="\n".join(text_lines).strip())
            )

        if not blocks:
            raise ValueError(
                "Aucun bloc de sous-titre reconnu. Vérifiez que le fichier est bien au format .srt standard."
            )
        return cls(blocks, source_path=path)

    def write(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for b in self.blocks:
                f.write(f"{b.index}\n{b.timing}\n{b.text}\n\n")


# ---------------------------------------------------------------------------
# Moteurs de traduction
# ---------------------------------------------------------------------------
def _chunk(lst: List, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


class TranslationEngine(ABC):
    """Interface commune à tous les moteurs de traduction."""

    def __init__(self, batch_size: int):
        self.batch_size = batch_size

    @abstractmethod
    def translate(
        self,
        texts: List[str],
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        """Traduit une liste de textes et retourne la liste traduite (même ordre)."""
        raise NotImplementedError


class DeepLEngine(TranslationEngine):
    """Moteur de traduction basé sur l'API DeepL."""

    def __init__(self, source: str = "EN", target: str = "FR", batch_size: int = 45):
        super().__init__(batch_size)
        self.source = source
        self.target = target

    def translate(
        self,
        texts: List[str],
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        try:
            import deepl
        except ImportError as e:
            raise TranslationEngineError(
                "Le module 'deepl' n'est pas installé (pip install deepl --break-system-packages)."
            ) from e

        api_key = os.environ.get("DEEPL_API_KEY")
        if not api_key:
            raise MissingApiKeyError("Variable d'environnement DEEPL_API_KEY manquante.")

        translator = deepl.Translator(api_key)
        results: List[str] = []
        batches = list(_chunk(texts, self.batch_size))

        for i, batch in enumerate(batches, start=1):
            translations = translator.translate_text(
                batch,
                source_lang=self.source if self.source.upper() != "AUTO" else None,
                target_lang=self.target,
            )
            results.extend(t.text for t in translations)
            if progress_cb:
                progress_cb(i, len(batches))
        return results


class AnthropicEngine(TranslationEngine):
    """Moteur de traduction basé sur l'API Anthropic (Claude)."""

    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-sonnet-4-6"

    def __init__(self, target_label: str = "français", batch_size: int = 40):
        super().__init__(batch_size)
        self.target_label = target_label

    def translate(
        self,
        texts: List[str],
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        try:
            import requests
        except ImportError as e:
            raise TranslationEngineError(
                "Le module 'requests' n'est pas installé (pip install requests --break-system-packages)."
            ) from e

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingApiKeyError("Variable d'environnement ANTHROPIC_API_KEY manquante.")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        results: List[str] = []
        batches = list(_chunk(texts, self.batch_size))

        for i, batch in enumerate(batches, start=1):
            results.extend(self._translate_batch(batch, headers, requests))
            if progress_cb:
                progress_cb(i, len(batches))
            time.sleep(0.3)

        return results

    def _translate_batch(self, batch: List[str], headers: dict, requests_module) -> List[str]:
        numbered = "\n".join(f"{j+1}. {line}" for j, line in enumerate(batch))
        prompt = (
            f"Traduis les répliques de sous-titres suivantes vers le {self.target_label}. "
            "Conserve le ton familier/oral du dialogue, garde chaque réplique sur une seule ligne, "
            "et renvoie UNIQUEMENT la liste numérotée traduite, dans le même ordre, sans autre texte.\n\n"
            f"{numbered}"
        )
        payload = {
            "model": self.MODEL,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests_module.post(self.API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        raw_text = "".join(b.get("text", "") for b in data.get("content", []))

        lines = [l.strip() for l in raw_text.strip().split("\n") if l.strip()]
        parsed = []
        for l in lines:
            m = re.match(r"^\d+\.\s*(.*)$", l)
            parsed.append(m.group(1) if m else l)

        if len(parsed) != len(batch):
            raise TranslationEngineError(
                f"Lot: {len(batch)} répliques attendues, {len(parsed)} reçues du modèle."
            )
        return parsed


# ---------------------------------------------------------------------------
# Orchestrateur haut niveau
# ---------------------------------------------------------------------------
class SubtitleTranslator:
    """Applique un TranslationEngine à un SrtDocument."""

    def __init__(self, engine: TranslationEngine):
        self.engine = engine

    def translate(
        self,
        document: SrtDocument,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Traduit le document en place. Retourne le nombre de répliques traduites."""
        translated_texts = self.engine.translate(document.texts, progress_cb=progress_cb)
        document.apply_translations(translated_texts)
        return len(document)

    def translate_file(
        self,
        input_path: str,
        output_path: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Lit un .srt, le traduit, et écrit le résultat. Retourne le nombre de répliques."""
        document = SrtDocument.from_file(input_path)
        count = self.translate(document, progress_cb=progress_cb)
        document.write(output_path)
        return count


# ---------------------------------------------------------------------------
# Fabrique pratique : engine="deepl"/"anthropic" -> instance de moteur
# ---------------------------------------------------------------------------
ENGINES = {
    "deepl": DeepLEngine,
    "anthropic": AnthropicEngine,
}


def create_engine(name: str, **kwargs) -> TranslationEngine:
    """Crée un moteur par son nom : create_engine('deepl', source='EN', target='FR')."""
    engine_cls = ENGINES.get(name)
    if engine_cls is None:
        raise ValueError(f"Moteur inconnu : {name!r} (attendu: {list(ENGINES)})")
    return engine_cls(**kwargs)
