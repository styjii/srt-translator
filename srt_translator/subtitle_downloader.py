"""
subtitle_downloader.py — Téléchargement de sous-titres depuis YouTube et autres plateformes
------------------------------------------------------------------------------------------------
Utilise yt-dlp (successeur actif de youtube-dl) pour récupérer les sous-titres
(officiels ou générés automatiquement) d'une vidéo, SANS télécharger la vidéo
elle-même. Fonctionne avec YouTube et la plupart des plateformes supportées
par yt-dlp (Vimeo, Dailymotion, Twitch VOD, etc.).

Installation :
    pip install yt-dlp --break-system-packages

Exemple d'utilisation en tant que module :

    from subtitle_downloader import SubtitleDownloader

    downloader = SubtitleDownloader(lang="fr", auto_generated=True, output_dir="./subs")
    fichiers = downloader.download("https://www.youtube.com/watch?v=XXXXXXXXXXX")
    print(fichiers)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional


class SubtitleDownloadError(RuntimeError):
    pass


class SubtitleDownloader:
    """
    Télécharge les sous-titres d'une vidéo en ligne via yt-dlp, sans télécharger
    la vidéo. Respecte les mêmes sous-titres que ceux proposés publiquement par
    la plateforme (officiels ou générés automatiquement).
    """

    def __init__(
        self,
        lang: str = "en",
        auto_generated: bool = True,
        output_dir: str = ".",
        fmt: str = "srt",
    ):
        """
        lang           : code langue des sous-titres à récupérer (ex: "en", "fr", "ja")
        auto_generated : si True, accepte aussi les sous-titres auto-générés
                         (utile si aucun sous-titre officiel n'existe)
        output_dir     : dossier où écrire les fichiers de sous-titres
        fmt            : format cible ("srt", "vtt", "best", ...)
        """
        self.lang = lang
        self.auto_generated = auto_generated
        self.output_dir = Path(output_dir)
        self.fmt = fmt
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def list_available_subtitles(self, url: str) -> dict:
        """
        Renvoie les sous-titres disponibles pour une vidéo, sans rien télécharger.
        Structure : {"officiels": [...codes langue...], "auto_generes": [...]}
        """
        try:
            import yt_dlp
        except ImportError as e:
            raise SubtitleDownloadError(
                "Le module 'yt-dlp' n'est pas installé (pip install yt-dlp --break-system-packages)."
            ) from e

        opts = {"quiet": True, "skip_download": True, "no_warnings": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise SubtitleDownloadError(f"Impossible de lire cette vidéo : {e}") from e

        return {
            "officiels": sorted(info.get("subtitles", {}).keys()),
            "auto_generes": sorted(info.get("automatic_captions", {}).keys()),
        }

    def download(self, url: str) -> List[Path]:
        """
        Télécharge les sous-titres pour la langue configurée.
        Retourne la liste des chemins de fichiers écrits.
        Lève SubtitleDownloadError si aucun sous-titre n'est disponible dans
        cette langue.
        """
        try:
            import yt_dlp
        except ImportError as e:
            raise SubtitleDownloadError(
                "Le module 'yt-dlp' n'est pas installé (pip install yt-dlp --break-system-packages)."
            ) from e

        outtmpl = str(self.output_dir / "%(title)s.%(ext)s")

        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": self.auto_generated,
            "subtitleslangs": [self.lang],
            "subtitlesformat": self.fmt,
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
        }

        before = set(self.output_dir.glob("*"))

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            raise SubtitleDownloadError(f"Échec du téléchargement : {e}") from e

        after = set(self.output_dir.glob("*"))
        new_files = sorted(after - before)

        subtitle_files = [f for f in new_files if f.suffix in (".srt", ".vtt", ".ass")]

        if not subtitle_files:
            raise SubtitleDownloadError(
                f"Aucun sous-titre trouvé pour la langue '{self.lang}' sur cette vidéo. "
                "Utilisez list_available_subtitles() pour voir les langues disponibles."
            )

        return subtitle_files
