"""Command-line interface for poker assistant."""

import argparse
import sys
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .config import Config
from .windows.detector import WindowDetector
from .ui.overlay import OverlayWindow
from .ocr.calibrate_gui import CalibrationGUI
from .telemetry.logger import setup_logging


app = typer.Typer(
    name="poker-assistant",
    help="Assistant IA Poker en Local - Analyse stratégique via OCR et Ollama",
    no_args_is_help=True,
)

console = Console()


@app.command()
def run(
    room: Optional[str] = typer.Option(None, "--room", "-r", help="Room to use (winamax, pmu)"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Run the poker assistant."""
    try:
        # Setup logging
        setup_logging(debug=debug, verbose=verbose)
        
        # Load config
        config = Config.load(config_file)
        
        # Auto-detect room if not specified
        if not room:
            detector = WindowDetector()
            detected_room = detector.detect_poker_room()
            if detected_room:
                room = detected_room
                console.print(f"[green]Auto-detected room: {room}[/green]")
            else:
                console.print("[red]No poker room detected. Please specify --room[/red]")
                raise typer.Exit(1)
        
        # Validate room
        if room not in config.available_rooms:
            console.print(f"[red]Unknown room: {room}. Available: {config.available_rooms}[/red]")
            raise typer.Exit(1)
        
        console.print(f"[blue]Starting poker assistant for room: {room}[/blue]")
        
        # Start overlay
        overlay = OverlayWindow(config=config, room=room)
        overlay.run()
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if debug:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def calibrate(
    room: str = typer.Argument(..., help="Room to calibrate (winamax, pmu)"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
) -> None:
    """Calibrate ROIs for a poker room."""
    try:
        config = Config.load()
        
        if room not in config.available_rooms:
            console.print(f"[red]Unknown room: {room}. Available: {config.available_rooms}[/red]")
            raise typer.Exit(1)
        
        console.print(f"[blue]Starting calibration for room: {room}[/blue]")
        
        # Start calibration GUI
        calibrator = CalibrationGUI(config=config, room=room)
        calibrator.run()
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Calibration cancelled[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if debug:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def detect() -> None:
    """Detect poker windows."""
    try:
        detector = WindowDetector()
        windows = detector.get_all_windows()
        
        table = Table(title="Detected Windows")
        table.add_column("Title", style="cyan")
        table.add_column("Class", style="magenta")
        table.add_column("PID", style="green")
        table.add_column("Rect", style="yellow")
        table.add_column("Score", style="red")
        
        for window in windows:
            score = detector.score_window(window)
            table.add_row(
                window.title[:50] + "..." if len(window.title) > 50 else window.title,
                window.class_name,
                str(window.pid),
                f"{window.rect}",
                f"{score:.2f}" if score else "N/A"
            )
        
        console.print(table)
        
        # Show best match
        best_window = detector.select_best_poker_window()
        if best_window:
            console.print(f"\n[green]Best match: {best_window.title}[/green]")
        else:
            console.print("\n[yellow]No poker window detected[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def rooms() -> None:
    """List available rooms."""
    try:
        config = Config.load()
        
        table = Table(title="Available Rooms")
        table.add_column("Room", style="cyan")
        table.add_column("Config File", style="magenta")
        table.add_column("Status", style="green")
        
        for room in config.available_rooms:
            config_file = config.get_room_config_path(room)
            status = "✓" if config_file.exists() else "✗"
            table.add_row(room, str(config_file), status)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def test_ocr(
    room: str = typer.Argument(..., help="Room to test"),
    roi: str = typer.Option("pot", "--roi", "-r", help="ROI to test"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
) -> None:
    """Test OCR on specific ROI."""
    try:
        config = Config.load()
        
        if room not in config.available_rooms:
            console.print(f"[red]Unknown room: {room}[/red]")
            raise typer.Exit(1)
        
        console.print(f"[blue]Testing OCR for room: {room}, ROI: {roi}[/blue]")
        
        # TODO: Implement OCR testing
        console.print("[yellow]OCR testing not yet implemented[/yellow]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if debug:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    try:
        from . import __version__
        
        panel = Panel(
            f"[bold blue]Poker Assistant[/bold blue]\n"
            f"Version: {__version__}\n"
            f"Python: {sys.version.split()[0]}\n"
            f"Platform: {sys.platform}",
            title="Version Info",
            border_style="blue"
        )
        console.print(panel)
        
    except ImportError:
        console.print("[yellow]Version not available[/yellow]")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
