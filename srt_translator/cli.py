"""
app.py — CLI de traduction de sous-titres .srt (Typer + Rich)
-----------------------------------------------------------------
Installation :
    pip install typer rich deepl requests --break-system-packages

Utilisation :
    python3 app.py traduire anime.srt sous_titres_fr.srt
    python3 app.py traduire anime.srt sous_titres_fr.srt --engine anthropic
    python3 app.py traduire anime.srt sous_titres_fr.srt --source EN --target FR
    python3 app.py --help
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .subtitle_downloader import SubtitleDownloadError, SubtitleDownloader
from .translate_srt import (
    MissingApiKeyError,
    SrtDocument,
    SubtitleTranslator,
    TranslationEngineError,
    create_engine,
)

# Charge automatiquement les variables du fichier .env (s'il existe) dans
# os.environ, sans écraser les variables déjà définies dans le shell.
load_dotenv()

app = typer.Typer(
    name="srt-translate",
    help="🎬 Traduit des fichiers de sous-titres .srt (DeepL ou Claude).",
    add_completion=True,
)
console = Console()


class Engine(str):
    DEEPL = "deepl"
    ANTHROPIC = "anthropic"


def _check_api_key(engine: str) -> Optional[str]:
    if engine == "deepl" and not os.environ.get("DEEPL_API_KEY"):
        return "DEEPL_API_KEY"
    if engine == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY"
    return None


@app.command()
def traduire(
    entree: Path = typer.Argument(..., exists=True, readable=True, help="Fichier .srt source"),
    sortie: Path = typer.Argument(..., help="Fichier .srt traduit à créer"),
    engine: str = typer.Option("deepl", "--engine", "-e", help="Moteur : 'deepl' ou 'anthropic'"),
    source: str = typer.Option("EN", "--source", "-s", help="Langue source (code DeepL, ex: EN)"),
    target: str = typer.Option("FR", "--target", "-t", help="Langue cible (code DeepL, ex: FR)"),
):
    """Traduit un fichier .srt et écrit le résultat dans un nouveau fichier."""

    missing = _check_api_key(engine)
    if missing:
        console.print(
            Panel(
                f"[bold red]Clé API manquante[/bold red]\n\n"
                f"La variable d'environnement [bold]{missing}[/bold] n'est pas définie.\n"
                f"Exportez-la avant de relancer :\n\n"
                f"  [cyan]export {missing}=\"votre_cle_ici\"[/cyan]",
                title="⚠️  Erreur de configuration",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]📖 Lecture de[/bold cyan] {entree} ...")
    try:
        document = SrtDocument.from_file(str(entree))
    except ValueError as e:
        console.print(f"[bold red]Erreur de lecture :[/bold red] {e}")
        raise typer.Exit(code=1)

    console.print(f"[green]✓[/green] {len(document)} répliques détectées.\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Traduction en cours[/bold blue]"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("• lot {task.fields[done]}/{task.fields[total_batches]}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("traduction", total=100, done=0, total_batches=1)

        def on_progress(done: int, total: int):
            progress.update(
                task_id,
                completed=int((done / total) * 100),
                done=done,
                total_batches=total,
            )

        try:
            engine_instance = create_engine(engine, source=source, target=target) \
                if engine == "deepl" else create_engine(engine)
            translator = SubtitleTranslator(engine_instance)
            count = translator.translate(document, progress_cb=on_progress)
            document.write(str(sortie))
        except MissingApiKeyError as e:
            console.print(f"\n[bold red]Erreur :[/bold red] {e}")
            raise typer.Exit(code=1)
        except TranslationEngineError as e:
            console.print(f"\n[bold red]Erreur du moteur de traduction :[/bold red] {e}")
            raise typer.Exit(code=1)
        except Exception as e:
            console.print(f"\n[bold red]Erreur inattendue :[/bold red] {e}")
            raise typer.Exit(code=1)

    console.print(
        Panel(
            f"[bold green]{count}[/bold green] répliques traduites avec succès.\n"
            f"Fichier écrit dans : [bold]{sortie}[/bold]",
            title="✅ Terminé",
            border_style="green",
        )
    )


@app.command()
def telecharger(
    url: str = typer.Argument(..., help="URL de la vidéo (YouTube ou autre plateforme supportée par yt-dlp)"),
    lang: str = typer.Option("en", "--lang", "-l", help="Code langue des sous-titres à récupérer"),
    auto: bool = typer.Option(
        True, "--auto/--no-auto", help="Accepter les sous-titres générés automatiquement si aucun officiel n'existe"
    ),
    sortie: Path = typer.Option(Path("."), "--output", "-o", help="Dossier où écrire le fichier de sous-titres"),
    lister: bool = typer.Option(
        False, "--lister", help="Lister les langues disponibles pour cette vidéo, sans rien télécharger"
    ),
):
    """Télécharge les sous-titres d'une vidéo (sans télécharger la vidéo elle-même)."""
    downloader = SubtitleDownloader(lang=lang, auto_generated=auto, output_dir=str(sortie))

    if lister:
        console.print(f"[bold cyan]🔍 Recherche des sous-titres disponibles pour[/bold cyan] {url} ...")
        try:
            dispo = downloader.list_available_subtitles(url)
        except SubtitleDownloadError as e:
            console.print(f"[bold red]Erreur :[/bold red] {e}")
            raise typer.Exit(code=1)

        table = Table(title="Sous-titres disponibles")
        table.add_column("Type", style="cyan")
        table.add_column("Langues", style="white")
        table.add_row("Officiels", ", ".join(dispo["officiels"]) or "(aucun)")
        table.add_row("Auto-générés", ", ".join(dispo["auto_generes"]) or "(aucun)")
        console.print(table)
        return

    console.print(f"[bold cyan]⬇️  Téléchargement des sous-titres ({lang})[/bold cyan] depuis {url} ...")
    try:
        fichiers = downloader.download(url)
    except SubtitleDownloadError as e:
        console.print(f"\n[bold red]Erreur :[/bold red] {e}")
        console.print(
            "[dim]Astuce : utilisez --lister pour voir les langues réellement disponibles pour cette vidéo.[/dim]"
        )
        raise typer.Exit(code=1)

    console.print(
        Panel(
            "\n".join(f"[bold]{f}[/bold]" for f in fichiers),
            title=f"✅ {len(fichiers)} fichier(s) de sous-titres téléchargé(s)",
            border_style="green",
        )
    )


@app.command()
def infos(
    entree: Path = typer.Argument(..., exists=True, readable=True, help="Fichier .srt à inspecter"),
):
    """Affiche des informations sur un fichier .srt sans le traduire."""
    document = SrtDocument.from_file(str(entree))

    table = Table(title=f"Aperçu de {entree.name}")
    table.add_column("Index", style="cyan", justify="right")
    table.add_column("Timing", style="magenta")
    table.add_column("Texte", style="white")

    for b in list(document)[:5]:
        table.add_row(b.index, b.timing, b.text[:50])

    console.print(table)
    console.print(f"\n[bold]{len(document)}[/bold] répliques au total.")


if __name__ == "__main__":
    app()
