# 🎬 SRT Translator

Un outil en ligne de commande pour traduire des fichiers de sous-titres `.srt` (DeepL ou Claude), avec une interface stylée grâce à [Typer](https://typer.tiangolo.com/) et [Rich](https://rich.readthedocs.io/).

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## ✨ Fonctionnalités

- Téléchargement des sous-titres d'une vidéo (YouTube et autres plateformes) via `yt-dlp`, sans télécharger la vidéo elle-même
- Parseur `.srt` robuste (ligne par ligne, sans risque de blocage sur de gros fichiers)
- Deux moteurs de traduction interchangeables : **DeepL** ou **Claude (Anthropic)**
- Barre de progression animée pendant la traduction par lots
- Commande `infos` pour inspecter un fichier sans le traduire
- Architecture orientée objet, facile à étendre avec un nouveau moteur de traduction
- Conserve intacts les numéros de séquence et les timecodes originaux

---

## 📁 Structure du projet

```
srt-translator/
├── pyproject.toml          # Métadonnées du package + point d'entrée CLI
├── requirements.txt        # Dépendances (alternative à pyproject.toml)
├── srt_translator/
│   ├── __init__.py
│   ├── cli.py                    # Interface CLI (Typer + Rich)
│   ├── translate_srt.py          # Module métier : traduction (parsing, moteurs, orchestration)
│   └── subtitle_downloader.py    # Module métier : téléchargement de sous-titres (yt-dlp)
├── .env.example            # Modèle de configuration des clés API
├── .gitignore
├── LICENSE                 # Licence MIT
└── README.md
```

---

## ⚙️ Installation

```bash
git clone https://github.com/styjii/srt-translator.git
cd srt-translator
pip install -e . --break-system-packages
```

> `--break-system-packages` est nécessaire sur certains environnements Linux récents (Debian/Ubuntu) qui protègent l'installation Python système. Omettez-le si vous utilisez un environnement virtuel (`venv`).
>
> Le mode éditable (`-e`) installe une commande `srt-translate` disponible partout sur votre système, tout en gardant le code lié au dépôt source : toute modification du code est immédiatement prise en compte, sans réinstallation.

**Alternative** (sans installer la commande `srt-translate`, juste les dépendances) :

```bash
pip install -r requirements.txt --break-system-packages
python3 -m srt_translator.cli --help
```

### Clés API

Copiez le modèle fourni et renseignez vos vraies clés :

```bash
cp .env.example .env
```

Éditez ensuite `.env` :

```dotenv
# Au moins une des deux clés selon le moteur utilisé
DEEPL_API_KEY=votre_cle_deepl
ANTHROPIC_API_KEY=votre_cle_anthropic
```

Le fichier `.env` est automatiquement chargé au démarrage (via `python-dotenv`) et n'est **jamais commité** grâce au `.gitignore` fourni.

---

## 🚀 Utilisation

```bash
# Aide générale
srt-translate --help

# Lister les langues de sous-titres disponibles pour une vidéo
srt-translate telecharger "https://youtube.com/watch?v=XXXXX" --lister

# Télécharger les sous-titres d'une vidéo (YouTube ou autre plateforme yt-dlp)
srt-translate telecharger "https://youtube.com/watch?v=XXXXX" --lang en -o ./subs

# Aperçu d'un fichier .srt sans le traduire
srt-translate infos anime.srt

# Traduire avec DeepL (par défaut, EN → FR)
srt-translate traduire anime.srt sous_titres_fr.srt

# Traduire avec Claude
srt-translate traduire anime.srt sous_titres_fr.srt --engine anthropic

# Spécifier les langues source/cible (DeepL)
srt-translate traduire anime.srt sous_titres_fr.srt --source EN --target FR
```

### Workflow complet : télécharger puis traduire

```bash
srt-translate telecharger "https://youtube.com/watch?v=XXXXX" --lang en -o ./subs
srt-translate traduire ./subs/nom_video.en.srt sous_titres_fr.srt
```

> ℹ️ La commande `telecharger` ne récupère que les sous-titres publiquement proposés par la plateforme (officiels ou générés automatiquement) — jamais la vidéo elle-même. Assurez-vous d'avoir le droit d'utiliser le contenu téléchargé selon les conditions d'utilisation de la plateforme concernée.

### Exemple de sortie

```
❯ srt-translate traduire anime.srt sous_titres_fr.srt
📖 Lecture de anime.srt ...
✓ 5816 répliques détectées.

Traduction en cours ████████████████████░░░░  82% • lot 12/15  00:01:04

╭──────────────────────── ✅ Terminé ────────────────────────╮
│ 5816 répliques traduites avec succès.                      │
│ Fichier écrit dans : sous_titres_fr.srt                    │
╰──────────────────────────────────────────────────────────────╯
```

---

## 🏗️ Architecture

Le module `srt_translator/translate_srt.py` est organisé autour de quelques classes :

| Classe | Rôle |
|---|---|
| `SrtDocument` | Charge un `.srt` (`from_file`), expose les blocs (`SubtitleBlock`), écrit le résultat (`write`) |
| `TranslationEngine` | Classe abstraite définissant l'interface `translate(texts, progress_cb)` |
| `DeepLEngine` | Implémentation du moteur DeepL |
| `AnthropicEngine` | Implémentation du moteur Claude |
| `SubtitleTranslator` | Orchestre un `TranslationEngine` sur un `SrtDocument` |
| `create_engine(nom, **kwargs)` | Fabrique un moteur à partir de son nom (`"deepl"` / `"anthropic"`) |

Le module `srt_translator/subtitle_downloader.py` gère le téléchargement :

| Classe/méthode | Rôle |
|---|---|
| `SubtitleDownloader` | Encapsule `yt-dlp` pour récupérer uniquement les sous-titres d'une vidéo |
| `.list_available_subtitles(url)` | Liste les langues disponibles (officielles/auto-générées) sans télécharger |
| `.download(url)` | Télécharge les sous-titres dans la langue configurée |

### Ajouter un nouveau moteur de traduction

```python
from srt_translator.translate_srt import TranslationEngine

class GoogleTranslateEngine(TranslationEngine):
    def translate(self, texts, progress_cb=None):
        # votre implémentation ici
        ...
```

Puis l'enregistrer dans le dictionnaire `ENGINES` du module.

---

## 🧩 Utilisation en tant que module Python

```python
from srt_translator.translate_srt import SrtDocument, DeepLEngine, SubtitleTranslator

document = SrtDocument.from_file("input.srt")
engine = DeepLEngine(source="EN", target="FR")
translator = SubtitleTranslator(engine)

translator.translate(document, progress_cb=lambda done, total: print(f"{done}/{total}"))
document.write("output_fr.srt")
```

---

## 📋 Prérequis

- Python 3.9+
- Un compte [DeepL API](https://www.deepl.com/pro-api) **et/ou** une clé [Anthropic API](https://console.anthropic.com/)

---

## 🤝 Contribuer

Les contributions sont bienvenues : ouvrez une *issue* ou une *pull request*.

1. Forkez le projet
2. Créez une branche (`git checkout -b feature/ma-fonctionnalite`)
3. Commitez vos changements (`git commit -m 'Ajout de ma fonctionnalité'`)
4. Poussez la branche (`git push origin feature/ma-fonctionnalite`)
5. Ouvrez une Pull Request

---

## 📄 Licence

Ce projet est distribué sous licence [MIT](LICENSE) — © 2026 [Styjii](https://github.com/styjii).

Vous êtes libre de l'utiliser, le modifier, le redistribuer, y compris à des fins commerciales, à condition de conserver la notice de copyright.
