"""
Rich progress display for terminal output.
"""
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProgressStats:
    """Statistics for progress display."""
    total_entries: int = 0
    processed: int = 0
    success: int = 0
    warnings: int = 0
    errors: int = 0
    current_entry: str = ""
    current_task: str = ""


class ProgressDisplay:
    """Rich terminal progress display."""
    
    def __init__(self):
        self.console = Console()
        self.stats = ProgressStats()
        self._progress: Optional[Progress] = None
        self._live: Optional[Live] = None
        self._main_task = None
    
    def _create_stats_table(self) -> Table:
        """Create a statistics table."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="dim")
        table.add_column("Value", style="bold")
        
        table.add_row("📚 Total Entries", str(self.stats.total_entries))
        table.add_row("✅ Success", f"[green]{self.stats.success}[/green]")
        table.add_row("⚠️  Warnings", f"[yellow]{self.stats.warnings}[/yellow]")
        table.add_row("❌ Errors", f"[red]{self.stats.errors}[/red]")
        
        return table
    
    def _create_display(self) -> Panel:
        """Create the main display panel."""
        layout = Layout()
        
        # Status text
        status_text = Text()
        status_text.append("Current: ", style="dim")
        status_text.append(self.stats.current_entry or "N/A", style="cyan bold")
        status_text.append("\n")
        status_text.append("Task: ", style="dim")
        status_text.append(self.stats.current_task or "Initializing...", style="white")
        
        return Panel(
            status_text,
            title="[bold blue]📖 Bibliography Checker[/bold blue]",
            border_style="blue"
        )
    
    @contextmanager
    def progress_context(self, total: int, description: str = "Processing"):
        """Context manager for progress display."""
        self.stats.total_entries = total
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=False
        ) as progress:
            self._progress = progress
            self._main_task = progress.add_task(description, total=total)
            try:
                yield self
            finally:
                self._progress = None
                self._main_task = None
    
    def update(self, entry_key: str = "", task: str = "", advance: int = 0):
        """Update progress display."""
        if entry_key:
            self.stats.current_entry = entry_key
        if task:
            self.stats.current_task = task
        
        if self._progress and self._main_task is not None:
            desc = f"[cyan]{entry_key}[/cyan] - {task}" if entry_key else task
            self._progress.update(self._main_task, description=desc, advance=advance)
            self.stats.processed += advance
    
    def mark_success(self):
        """Mark current entry as successful."""
        self.stats.success += 1
    
    def mark_warning(self):
        """Mark current entry with warning."""
        self.stats.warnings += 1
    
    def mark_error(self):
        """Mark current entry as error."""
        self.stats.errors += 1
    
    def print_header(self, title: str):
        """Print a section header."""
        self.console.print()
        self.console.print(Panel(
            f"[bold]{title}[/bold]",
            border_style="blue",
            expand=False
        ))
    
    def print_status(self, message: str, style: str = ""):
        """Print a status message."""
        self.console.print(f"  {message}", style=style)
    
    def print_success(self, message: str):
        """Print a success message."""
        self.console.print(f"  [green]✓[/green] {message}")
    
    def print_warning(self, message: str):
        """Print a warning message."""
        self.console.print(f"  [yellow]⚠[/yellow] {message}")
    
    def print_error(self, message: str):
        """Print an error message."""
        self.console.print(f"  [red]✗[/red] {message}")
    
    def print_info(self, message: str):
        """Print an info message."""
        self.console.print(f"  [blue]ℹ[/blue] {message}")
    
    def print_detailed_summary(self, bib_stats: dict, latex_stats: dict, output_dir: str):
        """Print a beautiful detailed summary table (Issues only)."""
        self.console.print()
        
        # Create Bibliography Issues Table
        bib_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
        bib_table.add_column("📚 Bibliography Issues", style="white")
        bib_table.add_column("Count", justify="right", style="bold red")
        
        for label, value in bib_stats.items():
            bib_table.add_row(label, str(value))
            
        # Create LaTeX Issues Table - Fine-grained Breakdown
        latex_table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
        latex_table.add_column("📋 LaTeX Quality Issues (Fine-grained)", style="white")
        latex_table.add_column("Count", justify="right", style="bold yellow")
        
        if not latex_stats:
            latex_table.add_row("[green]No issues found[/green]", "0")
        else:
            # Sort by count descending
            for category, count in sorted(latex_stats.items(), key=lambda x: x[1], reverse=True):
                latex_table.add_row(category, str(count))
            
        # Combine into a single panel
        from rich.columns import Columns
        
        # If no bib issues, only show latex table
        content = []
        if bib_stats:
            content.append(bib_table)
        content.append(latex_table)
        
        summary_panel = Panel(
            Columns(content, expand=True),
            title="[bold red]⚠️ Issue Summary (Action Required)[/bold red]",
            border_style="red",
            padding=(1, 2)
        )
        
        self.console.print(summary_panel)
        
        # File meaning guide
        guide_table = Table(show_header=True, header_style="bold green", box=None, padding=(0, 2))
        guide_table.add_column("File Name", style="cyan")
        guide_table.add_column("Description", style="dim")
        
        guide_table.add_row("bibliography_report.md", "Detailed metadata and usage issues for each bib entry")
        guide_table.add_row("latex_quality_report.md", "Summary of all LaTeX writing and formatting issues")
        guide_table.add_row("line_by_line_report.md", "All LaTeX issues sorted by line number for easy fixing")
        guide_table.add_row("*_only_used.bib", "A cleaned version of your bib file containing only cited entries")
        
        self.console.print(Panel(
            guide_table,
            title="[bold green]Output Directory Guide[/bold green]",
            subtitle=f"Location: [blue underline]{output_dir}[/blue underline]",
            border_style="green",
            padding=(1, 1)
        ))
