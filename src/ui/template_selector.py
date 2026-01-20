"""
Interactive template selector for conference presets.

Provides a terminal UI for selecting a conference template
with information about requirements and rules.
"""
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.columns import Columns
from rich.text import Text

from ..templates.base_template import (
    ConferenceTemplate, 
    get_template, 
    get_all_templates,
    ConferenceField
)


class TemplateSelector:
    """Interactive terminal selector for conference templates."""
    
    def __init__(self):
        self.console = Console()
        self.templates = get_all_templates()
    
    def display_templates(self):
        """Display all available templates grouped by field."""
        self.console.clear()
        
        # Header
        self.console.print(Panel(
            "[bold blue]🎓 Conference Template Selector[/bold blue]\n"
            "[dim]Choose a conference template for submission checks[/dim]",
            border_style="blue"
        ))
        self.console.print()
        
        # Group by field
        fields = {
            ConferenceField.NLP: ("🗣️ NLP Conferences", []),
            ConferenceField.CV: ("👁️ Computer Vision Conferences", []),
            ConferenceField.ML: ("🧠 Machine Learning Conferences", []),
        }
        
        for template in self.templates.values():
            fields[template.field][1].append(template)
        
        # Display each field
        for field_enum, (title, templates) in fields.items():
            self.console.print(f"[bold cyan]{title}[/bold cyan]")
            
            table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
            table.add_column("ID", style="yellow", width=10)
            table.add_column("Conference", width=15)
            table.add_column("Pages", width=12)
            table.add_column("Key Requirements", style="dim")
            
            for template in templates:
                pages = f"{template.page_limit_review}→{template.page_limit_camera}"
                requirements = []
                if template.mandatory_sections:
                    requirements.append(f"Required: {', '.join(template.mandatory_sections)}")
                if template.extra_rules:
                    first_rule = list(template.extra_rules.values())[0]
                    requirements.append(first_rule[:50])
                
                table.add_row(
                    template.short_name,
                    template.name,
                    pages,
                    " | ".join(requirements) if requirements else "Standard format"
                )
            
            self.console.print(table)
            self.console.print()
    
    def display_template_details(self, template: ConferenceTemplate):
        """Display detailed information about a template."""
        self.console.print()
        self.console.print(Panel(
            f"[bold]{template.name}[/bold]",
            border_style="cyan"
        ))
        
        # Basic info
        info = Table(show_header=False, box=None, padding=(0, 2))
        info.add_column("Label", style="dim")
        info.add_column("Value")
        
        info.add_row("Style Package", f"[cyan]{template.style_package}[/cyan]")
        info.add_row("Page Limit (Review)", f"[yellow]{template.page_limit_review}[/yellow] pages")
        info.add_row("Page Limit (Camera)", f"[green]{template.page_limit_camera}[/green] pages")
        info.add_row("Double-Blind", "✓ Yes" if template.double_blind else "✗ No")
        
        if template.mandatory_sections:
            info.add_row("Mandatory Sections", ", ".join(template.mandatory_sections))
        if template.optional_sections:
            info.add_row("Optional Sections", ", ".join(template.optional_sections))
        
        self.console.print(info)
        
        # Extra rules
        if template.extra_rules:
            self.console.print()
            self.console.print("[bold]Special Requirements:[/bold]")
            for key, value in template.extra_rules.items():
                self.console.print(f"  • [dim]{key}:[/dim] {value}")
        
        self.console.print()
    
    def run(self) -> Optional[ConferenceTemplate]:
        """Run the interactive selector and return the chosen template."""
        while True:
            self.display_templates()
            
            # Get user input
            choice = Prompt.ask(
                "[bold]Enter template ID (or 'q' to quit, 'd <id>' for details)[/bold]",
                default="q"
            )
            
            if choice.lower() == 'q':
                return None
            
            # Handle details command
            if choice.lower().startswith('d '):
                template_id = choice[2:].strip().lower()
                template = get_template(template_id)
                if template:
                    self.display_template_details(template)
                    Prompt.ask("Press Enter to continue")
                else:
                    self.console.print(f"[red]Unknown template: {template_id}[/red]")
                    Prompt.ask("Press Enter to continue")
                continue
            
            # Try to get template
            template = get_template(choice)
            if template:
                self.console.print(f"[green]✓ Selected: {template.name}[/green]")
                return template
            else:
                self.console.print(f"[red]Unknown template: {choice}[/red]")
                self.console.print("[dim]Available: " + ", ".join(self.templates.keys()) + "[/dim]")
                Prompt.ask("Press Enter to continue")


def launch_template_selector() -> Optional[ConferenceTemplate]:
    """Launch the template selector and return the chosen template."""
    selector = TemplateSelector()
    return selector.run()


def list_templates(console: Console = None):
    """Print a simple list of available templates."""
    if console is None:
        console = Console()
    
    console.print("\n[bold]Available Conference Templates:[/bold]\n")
    
    templates = get_all_templates()
    
    # Group by field
    by_field = {}
    for t in templates.values():
        if t.field not in by_field:
            by_field[t.field] = []
        by_field[t.field].append(t)
    
    field_names = {
        ConferenceField.NLP: "NLP",
        ConferenceField.CV: "Computer Vision",
        ConferenceField.ML: "Machine Learning",
    }
    
    for field, field_templates in by_field.items():
        console.print(f"[cyan]{field_names[field]}:[/cyan]")
        for t in field_templates:
            console.print(f"  • [yellow]{t.short_name:8}[/yellow] - {t.name} ({t.page_limit_review}/{t.page_limit_camera} pages)")
    
    console.print()
