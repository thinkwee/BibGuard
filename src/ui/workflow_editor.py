"""
Interactive workflow editor for reference checking configuration.

Provides a terminal-based UI using rich for customizing the order
and enabled state of fetchers in the verification workflow.
"""
from typing import Optional
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text

from ..config.workflow import WorkflowConfig, get_default_workflow


class WorkflowEditor:
    """Interactive terminal editor for workflow configuration."""
    
    def __init__(self, config: Optional[WorkflowConfig] = None):
        self.console = Console()
        self.config = config or get_default_workflow()
        self.selected_index = 0
        self.modified = False
    
    def display_workflow(self):
        """Display current workflow configuration as a table."""
        self.console.clear()
        
        # Header
        self.console.print(Panel(
            "[bold blue]📋 Reference Check Workflow Editor[/bold blue]\n"
            "[dim]Customize the order and sources for metadata verification[/dim]",
            border_style="blue"
        ))
        
        # Instructions
        self.console.print()
        self.console.print("[dim]Commands: [cyan]u[/cyan]=move up, [cyan]d[/cyan]=move down, "
                          "[cyan]t[/cyan]=toggle, [cyan]s[/cyan]=save, [cyan]r[/cyan]=reset, [cyan]q[/cyan]=quit[/dim]")
        self.console.print()
        
        # Workflow table
        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("#", style="dim", width=3)
        table.add_column("Status", width=8)
        table.add_column("Source", width=25)
        table.add_column("Description", style="dim")
        
        for i, step in enumerate(self.config.steps):
            # Highlight selected row
            row_style = "reverse" if i == self.selected_index else ""
            
            # Status indicator
            if step.enabled:
                status = "[green]✓ ON[/green]"
            else:
                status = "[red]✗ OFF[/red]"
            
            # Priority number
            priority = f"{i + 1}"
            
            table.add_row(
                priority,
                status,
                step.display_name,
                step.description,
                style=row_style
            )
        
        self.console.print(table)
        self.console.print()
        
        # Current selection info
        if 0 <= self.selected_index < len(self.config.steps):
            step = self.config.steps[self.selected_index]
            info = Text()
            info.append("Selected: ", style="dim")
            info.append(step.display_name, style="cyan bold")
            info.append(f" (search type: {step.search_type})", style="dim")
            self.console.print(info)
        
        if self.modified:
            self.console.print("[yellow]* Unsaved changes[/yellow]")
    
    def run(self) -> WorkflowConfig:
        """Run the interactive editor loop."""
        while True:
            self.display_workflow()
            
            # Get user input
            try:
                cmd = Prompt.ask(
                    "\n[bold]Enter command[/bold]",
                    choices=["u", "d", "t", "s", "r", "q", "1", "2", "3", "4", "5", "6", "7", "8"],
                    default="q",
                    show_choices=False
                )
            except KeyboardInterrupt:
                cmd = "q"
            
            if cmd == "q":
                if self.modified:
                    if Confirm.ask("Discard unsaved changes?", default=False):
                        break
                else:
                    break
            elif cmd == "u":
                if self.config.move_step_up(self.selected_index):
                    self.selected_index -= 1
                    self.modified = True
            elif cmd == "d":
                if self.config.move_step_down(self.selected_index):
                    self.selected_index += 1
                    self.modified = True
            elif cmd == "t":
                self.config.toggle_step(self.selected_index)
                self.modified = True
            elif cmd == "s":
                self._save_workflow()
            elif cmd == "r":
                if Confirm.ask("Reset to default workflow?", default=False):
                    self.config = get_default_workflow()
                    self.selected_index = 0
                    self.modified = True
            elif cmd.isdigit():
                num = int(cmd)
                if 1 <= num <= len(self.config.steps):
                    self.selected_index = num - 1
        
        return self.config
    
    def _save_workflow(self):
        """Save workflow configuration to file."""
        default_path = Path.home() / ".bibguard" / "workflow.json"
        
        path_str = Prompt.ask(
            "Save to",
            default=str(default_path)
        )
        
        try:
            self.config.save(path_str)
            self.console.print(f"[green]✓ Saved to {path_str}[/green]")
            self.modified = False
        except Exception as e:
            self.console.print(f"[red]✗ Failed to save: {e}[/red]")
        
        Prompt.ask("Press Enter to continue")


def launch_workflow_editor(config_path: Optional[str] = None) -> WorkflowConfig:
    """Launch the workflow editor and return the resulting configuration."""
    config = None
    if config_path:
        try:
            config = WorkflowConfig.load(config_path)
        except FileNotFoundError:
            pass
    
    editor = WorkflowEditor(config)
    return editor.run()
