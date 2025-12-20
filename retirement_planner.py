#!/usr/bin/env python3
"""
Retirement Planner
Calculates retirement savings projections and analyzes retirement readiness.
"""

import argparse
from datetime import datetime
import sys

import yaml
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table as RLTable, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.enums import TA_CENTER
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend


class RetirementPlanner:
    def __init__(self, config_path='config.yaml'):
        """Initialize the retirement planner with configuration."""
        self.config = self._load_config(config_path)
        self.console = Console()
        self.validate_config()

    def _load_config(self, config_path):
        """Load configuration from YAML file."""
        with open(config_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)

    def validate_config(self):
        """Validate configuration parameters."""
        required_fields = [
            'current_age', 'retirement_age', 'life_expectancy',
            'accounts', 'expected_return_rate',
            'inflation_rate', 'annual_retirement_expenses'
        ]

        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required field: {field}")

        if self.config['current_age'] >= self.config['retirement_age']:
            raise ValueError("Current age must be less than retirement age")

        if self.config['retirement_age'] >= self.config['life_expectancy']:
            raise ValueError("Retirement age must be less than life expectancy")

        # Validate accounts
        if not self.config['accounts']:
            raise ValueError("At least one account must be configured")

    def calculate_accumulation_phase(self):
        """Calculate savings growth until retirement for multiple accounts."""
        years_to_retirement = self.config['retirement_age'] - self.config['current_age']
        return_rate = self.config['expected_return_rate']
        contribution_growth = self.config.get('contribution_growth_rate', 0)

        accounts = self.config['accounts']

        # Initialize each account
        account_balances = {name: acc['balance'] for name, acc in accounts.items()}
        account_contributions = {name: acc['annual_contribution'] for name, acc in accounts.items()}

        data = []

        for year in range(years_to_retirement + 1):
            age = self.config['current_age'] + year

            if year > 0:
                # Apply returns and contributions to each account
                for name, acc_config in accounts.items():
                    # Apply returns (per-account override via interest_rate; cash defaults to 0.0)
                    acct_rate = acc_config.get('interest_rate')
                    if acct_rate is None:
                        acct_rate = 0.0 if acc_config.get('type') == 'cash' else return_rate
                    account_balances[name] *= (1 + acct_rate)

                    # Add contribution (respecting limits if any)
                    contribution = account_contributions[name]
                    limit = acc_config.get('contribution_limit')
                    if limit:
                        contribution = min(contribution, limit)

                    account_balances[name] += contribution

                    # Grow contribution for next year
                    account_contributions[name] *= (1 + contribution_growth)

            # Calculate total balance and contribution
            total_balance = sum(account_balances.values())
            total_contribution = sum(account_contributions.values()) if year < years_to_retirement else 0

            row_data = {
                'Year': year,
                'Age': age,
                'Total_Balance': total_balance,
                'Total_Contribution': total_contribution
            }

            # Add individual account balances
            for name in accounts.keys():
                row_data[f'{name}_balance'] = account_balances[name]

            data.append(row_data)

        return pd.DataFrame(data), account_balances

    def calculate_retirement_phase(self, account_balances):
        """Calculate retirement spending with tax-aware withdrawals from multiple accounts."""
        years_in_retirement = self.config['life_expectancy'] - self.config['retirement_age']

        # Initialize account balances
        balances = account_balances.copy()
        accounts = self.config['accounts']
        withdrawal_order = self.config.get('withdrawal_order', list(accounts.keys()))

        annual_expenses = self.config['annual_retirement_expenses']
        expense_growth = self.config.get('expense_growth_rate', self.config['inflation_rate'])
        return_rate = self.config['expected_return_rate']
        inflation_rate = self.config['inflation_rate']
        retirement_tax_rate = self.config.get('retirement_tax_rate', 0.15)
        capital_gains_rate = self.config.get('capital_gains_rate', 0.15)

        # Social Security / Pension
        ss_amount = self.config.get('annual_social_security', 0)
        ss_start_age = self.config.get('social_security_start_age', self.config['retirement_age'])
        other_income = self.config.get('other_annual_income', 0)

        # Adjust initial expenses for inflation from now until retirement
        years_to_retirement = self.config['retirement_age'] - self.config['current_age']
        annual_expenses *= (1 + inflation_rate) ** years_to_retirement
        ss_amount *= (1 + inflation_rate) ** years_to_retirement
        other_income *= (1 + inflation_rate) ** years_to_retirement

        data = []

        for year in range(int(years_in_retirement) + 1):
            age = self.config['retirement_age'] + year

            # Calculate income
            social_security = ss_amount if age >= ss_start_age else 0
            total_income = social_security + other_income

            # Calculate gross withdrawal needed (before tax)
            after_tax_need = max(0, annual_expenses - total_income)

            # Withdraw from accounts based on strategy
            total_withdrawn = 0
            total_taxes = 0
            # Track gross withdrawals per account for reporting
            account_withdrawals = {name: 0 for name in accounts.keys()}

            if year > 0 and after_tax_need > 0:
                remaining_need = after_tax_need

                for account_name in withdrawal_order:
                    if remaining_need <= 0 or balances.get(account_name, 0) <= 0:
                        account_withdrawals[account_name] = 0
                        continue

                    account_type = accounts[account_name]['type']

                    # Calculate how much to withdraw based on account type
                    if account_type == 'roth':
                        # Roth: tax-free, withdraw exactly what we need
                        gross_withdrawal = min(remaining_need, balances[account_name])
                        taxes = 0
                        net_withdrawal = gross_withdrawal
                    elif account_type == 'pre_tax':
                        # Traditional: taxed as ordinary income
                        # Need to withdraw more to cover taxes
                        gross_withdrawal = min(remaining_need / (1 - retirement_tax_rate), balances[account_name])
                        taxes = gross_withdrawal * retirement_tax_rate
                        net_withdrawal = gross_withdrawal - taxes
                    elif account_type == 'cash':
                        # Cash: principal withdrawals are not taxed in this model
                        gross_withdrawal = min(remaining_need, balances[account_name])
                        taxes = 0
                        net_withdrawal = gross_withdrawal
                    elif account_type == 'taxable':
                        # Taxable: capital gains tax (assume 50% cost basis)
                        gains_portion = 0.5  # Assume half is gains
                        gross_withdrawal = min(remaining_need / (1 - gains_portion * capital_gains_rate),
                                             balances[account_name])
                        taxes = gross_withdrawal * gains_portion * capital_gains_rate
                        net_withdrawal = gross_withdrawal - taxes
                    else:
                        gross_withdrawal = min(remaining_need, balances[account_name])
                        taxes = 0
                        net_withdrawal = gross_withdrawal

                    balances[account_name] -= gross_withdrawal
                    account_withdrawals[account_name] = gross_withdrawal
                    total_withdrawn += gross_withdrawal
                    total_taxes += taxes
                    remaining_need -= net_withdrawal

            # Apply returns to remaining balances
            if year < years_in_retirement:
                for account_name, acc_config in accounts.items():
                    if balances.get(account_name, 0) > 0:
                        acct_rate = acc_config.get('interest_rate')
                        if acct_rate is None:
                            acct_rate = 0.0 if acc_config.get('type') == 'cash' else return_rate
                        balances[account_name] *= (1 + acct_rate)

            # Calculate total balance
            total_balance = sum(balances.values())

            row_data = {
                'Year': year,
                'Age': age,
                'Total_Balance': max(0, total_balance),
                'Annual_Expenses': annual_expenses,
                'Social_Security': social_security,
                'Other_Income': other_income,
                'Gross_Withdrawal': total_withdrawn,
                'Taxes_Paid': total_taxes,
                'Net_Withdrawal': total_withdrawn - total_taxes
            }

            # Add individual account balances
            for account_name in accounts.keys():
                row_data[f'{account_name}_balance'] = max(0, balances.get(account_name, 0))

            # Add individual account withdrawals (gross)
            for account_name in accounts.keys():
                row_data[f'{account_name}_withdrawal'] = account_withdrawals.get(account_name, 0)

            data.append(row_data)

            # Increase expenses for next year
            annual_expenses *= (1 + expense_growth)
            social_security *= (1 + inflation_rate) if social_security > 0 else 0
            other_income *= (1 + inflation_rate) if other_income > 0 else 0

            # Stop if balance reaches zero
            if total_balance <= 0:
                break

        return pd.DataFrame(data)

    def generate_full_projection(self):
        """Generate complete retirement projection."""
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]RETIREMENT PLANNER[/bold cyan]\n[dim]Full Projection Analysis[/dim]",
            border_style="cyan"
        ))

        # Accumulation phase
        accumulation_df, final_balances = self.calculate_accumulation_phase()
        retirement_df = self.calculate_retirement_phase(final_balances)

        self.console.print("\n[bold green]💰 ACCUMULATION PHASE[/bold green] [dim](Saving for Retirement)[/dim]\n")
        years_to_ret = self.config['retirement_age'] - self.config['current_age']
        accounts = self.config['accounts']

        # Show starting balances
        self.console.print(f"[cyan]Years until retirement:[/cyan] {years_to_ret}")
        self.console.print("\n[bold]Starting Account Balances:[/bold]")
        for name, acc in accounts.items():
            acc_type = acc['type']
            type_label = {'pre_tax': '(Pre-tax)', 'roth': '(Roth)', 'taxable': '(Taxable)'}
            self.console.print(f"  [cyan]{name}[/cyan] {type_label.get(acc_type, '')}: ${acc['balance']:,.2f}")

        total_start = sum(acc['balance'] for acc in accounts.values())
        self.console.print(f"  [bold green]Total:[/bold green] ${total_start:,.2f}")

        retirement_balance = accumulation_df.iloc[-1]['Total_Balance']
        self.console.print(
            "\n[bold green]✓[/bold green] "
            f"[green]Projected total at retirement (age {self.config['retirement_age']}):[/green] "
            f"[bold yellow]${retirement_balance:,.2f}[/bold yellow]"
        )

        # Show final account balances
        self.console.print("\n[bold]Account Balances at Retirement:[/bold]")
        for name in accounts.keys():
            balance = final_balances[name]
            self.console.print(f"  [cyan]{name}:[/cyan] ${balance:,.2f}")

        # Show accumulation summary
        self.console.print("\n[bold]Accumulation Summary (selected years):[/bold]")
        milestones = [0, len(accumulation_df)//4, len(accumulation_df)//2,
                     3*len(accumulation_df)//4, len(accumulation_df)-1]

        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Age", justify="right", style="cyan")
        table.add_column("Total Balance", justify="right", style="green")
        for name in accounts.keys():
            table.add_column(name.replace('_', ' ').title(), justify="right", style="yellow")

        for idx in milestones:
            row = accumulation_df.iloc[idx]
            row_data = [
                str(int(row['Age'])),
                f"${row['Total_Balance']:,.2f}"
            ]
            for name in accounts.keys():
                row_data.append(f"${row[f'{name}_balance']:,.2f}")
            table.add_row(*row_data)
        self.console.print(table)

        # Retirement phase
        self.console.print("\n[bold magenta]🏖️  RETIREMENT PHASE[/bold magenta] [dim](Spending Years)[/dim]\n")
        retirement_df = self.calculate_retirement_phase(final_balances)

        final_balance = retirement_df.iloc[-1]['Total_Balance']
        final_age = retirement_df.iloc[-1]['Age']

        self.console.print(f"[cyan]Years in retirement:[/cyan] {len(retirement_df) - 1}")
        self.console.print(f"[cyan]Starting retirement balance:[/cyan] ${retirement_balance:,.2f}")
        self.console.print(f"[cyan]Initial annual expenses:[/cyan] ${retirement_df.iloc[0]['Annual_Expenses']:,.2f}")

        # Show withdrawal strategy
        withdrawal_order = self.config.get('withdrawal_order', list(accounts.keys()))
        self.console.print(
            "[cyan]Withdrawal order:[/cyan] "
            + " → ".join([a.replace('_', ' ').title() for a in withdrawal_order])
        )

        if self.config.get('annual_social_security', 0) > 0:
            ss_start = self.config.get('social_security_start_age', self.config['retirement_age'])
            self.console.print(f"[cyan]Social Security starts at age:[/cyan] {ss_start}")

        self.console.print(
            "\n[bold green]✓[/bold green] "
            f"[green]Final balance at age {final_age}:[/green] "
            f"[bold yellow]${final_balance:,.2f}[/bold yellow]"
        )

        # Show retirement summary
        self.console.print("\n[bold]Retirement Summary (selected years):[/bold]")
        ret_milestones = [0, len(retirement_df)//4, len(retirement_df)//2,
                         3*len(retirement_df)//4, len(retirement_df)-1]

        table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        table.add_column("Age", justify="right", style="magenta")
        table.add_column("Total Balance", justify="right", style="green")
        table.add_column("Expenses", justify="right", style="red")
        table.add_column("Soc. Security", justify="right", style="blue")
        table.add_column("Taxes Paid", justify="right", style="red")
        table.add_column("Net Withdrawal", justify="right", style="yellow")

        for idx in ret_milestones:
            row = retirement_df.iloc[idx]
            table.add_row(
                str(int(row['Age'])),
                f"${row['Total_Balance']:,.2f}",
                f"${row['Annual_Expenses']:,.2f}",
                f"${row['Social_Security']:,.2f}",
                f"${row['Taxes_Paid']:,.2f}",
                f"${row['Net_Withdrawal']:,.2f}"
            )
        self.console.print(table)

        # Analysis
        self.console.print()

        if final_balance > 0 and final_age >= self.config['life_expectancy']:
            success_text = Text()
            success_text.append("✓ SUCCESS\n\n", style="bold green")
            success_text.append("You are projected to have ", style="white")
            success_text.append(f"${final_balance:,.2f}", style="bold yellow")
            success_text.append(f" remaining at age {final_age}\n\n", style="white")
            success_text.append(
                "Your retirement savings should last through your expected lifetime.",
                style="dim green"
            )

            self.console.print(Panel(success_text, title="[bold]Retirement Readiness Analysis[/bold]",
                                    border_style="green", box=box.DOUBLE))
        elif final_balance <= 0:
            warning_text = Text()
            warning_text.append("⚠️  WARNING\n\n", style="bold red")
            warning_text.append(f"Funds projected to run out at age {final_age}\n", style="red")
            warning_text.append(
                f"This is {self.config['life_expectancy'] - final_age:.0f} years before expected life expectancy.\n\n",
                style="yellow"
            )
            warning_text.append("Consider:\n", style="bold white")
            warning_text.append("  • Increasing annual contributions\n", style="cyan")
            warning_text.append("  • Working longer (delay retirement)\n", style="cyan")
            warning_text.append("  • Reducing retirement expenses\n", style="cyan")
            warning_text.append("  • Adjusting investment strategy", style="cyan")

            self.console.print(Panel(warning_text, title="[bold]Retirement Readiness Analysis[/bold]",
                                    border_style="red", box=box.DOUBLE))

        # Calculate key metrics
        total_start = sum(acc['balance'] for acc in accounts.values())
        total_contributed = accumulation_df['Total_Contribution'].sum()
        investment_gains = retirement_balance - total_start - total_contributed

        # Calculate total taxes paid in retirement
        total_taxes_paid = retirement_df['Taxes_Paid'].sum()

        self.console.print("\n[bold cyan]📊 Key Metrics[/bold cyan]")
        metrics_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        metrics_table.add_column(style="cyan")
        metrics_table.add_column(style="yellow", justify="right")

        metrics_table.add_row("Total contributions:", f"${total_contributed:,.2f}")
        metrics_table.add_row("Investment gains:", f"${investment_gains:,.2f}")
        metrics_table.add_row("Total accumulated:", f"[bold]${retirement_balance:,.2f}[/bold]")
        metrics_table.add_row("Total taxes paid (retirement):", f"${total_taxes_paid:,.2f}")

        # Calculate replacement ratio
        final_working_income = self.config.get('current_annual_income', 0)
        if final_working_income > 0:
            first_year_expense = retirement_df.iloc[1]['Annual_Expenses']
            replacement_ratio = (first_year_expense / final_working_income) * 100
            metrics_table.add_row("Income replacement ratio:", f"{replacement_ratio:.1f}%")

        self.console.print(metrics_table)

        results = {
            'accumulation': accumulation_df,
            'retirement': retirement_df,
            'retirement_balance': retirement_balance,
            'final_balance': final_balance,
            'final_age': final_age,
            'total_contributions': total_contributed,
            'investment_gains': investment_gains,
            'total_taxes_paid': total_taxes_paid,
            'success': final_balance > 0 and final_age >= self.config['life_expectancy']
        }

        # Save detailed reports
        accumulation_df.to_csv('accumulation_phase.csv', index=False)
        retirement_df.to_csv('retirement_phase.csv', index=False)

        # Generate PDF report
        pdf_filename = self.generate_pdf_report(results)

        self.console.print("\n[bold cyan]📁 Detailed Reports Saved[/bold cyan]")
        self.console.print("  [green]✓[/green] [cyan]accumulation_phase.csv[/cyan] - Year-by-year savings growth")
        self.console.print("  [green]✓[/green] [cyan]retirement_phase.csv[/cyan] - Year-by-year retirement spending")
        self.console.print(f"  [green]✓[/green] [cyan]{pdf_filename}[/cyan] - Complete retirement analysis report")
        self.console.print()

        return results

    def _create_charts(self, accumulation_df, retirement_df):
        """Create matplotlib charts for PDF."""
        accounts = self.config['accounts']

        # Chart 1: Account Growth During Accumulation
        _, ax1 = plt.subplots(figsize=(10, 6))

        for name in accounts.keys():
            ax1.plot(accumulation_df['Age'], accumulation_df[f'{name}_balance'] / 1000,
                    label=name.replace('_', ' ').title(), linewidth=2)

        ax1.plot(accumulation_df['Age'], accumulation_df['Total_Balance'] / 1000,
                label='Total', linewidth=3, linestyle='--', color='black')

        ax1.set_xlabel('Age', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Balance ($1000s)', fontsize=12, fontweight='bold')
        ax1.set_title('Account Growth During Accumulation Phase', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        plt.tight_layout()

        chart1_path = 'accumulation_chart.png'
        plt.savefig(chart1_path, dpi=150, bbox_inches='tight')
        plt.close()

        # Chart 2: Balance During Retirement
        _, ax2 = plt.subplots(figsize=(10, 6))

        ax2.plot(retirement_df['Age'], retirement_df['Total_Balance'] / 1000,
                label='Total Balance', linewidth=3, color='green')
        ax2.plot(retirement_df['Age'], retirement_df['Annual_Expenses'] / 1000,
                label='Annual Expenses', linewidth=2, color='red', linestyle='--')

        ax2.set_xlabel('Age', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Amount ($1000s)', fontsize=12, fontweight='bold')
        ax2.set_title('Balance and Expenses During Retirement', fontsize=14, fontweight='bold')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()

        chart2_path = 'retirement_chart.png'
        plt.savefig(chart2_path, dpi=150, bbox_inches='tight')
        plt.close()

        # Chart 3: Account Balances During Retirement
        _, ax3 = plt.subplots(figsize=(10, 6))

        for name in accounts.keys():
            if f'{name}_balance' in retirement_df.columns:
                ax3.fill_between(retirement_df['Age'], 0, retirement_df[f'{name}_balance'] / 1000,
                               label=name.replace('_', ' ').title(), alpha=0.7)

        ax3.set_xlabel('Age', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Balance ($1000s)', fontsize=12, fontweight='bold')
        ax3.set_title('Account Drawdown During Retirement', fontsize=14, fontweight='bold')
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
        plt.tight_layout()

        chart3_path = 'retirement_accounts_chart.png'
        plt.savefig(chart3_path, dpi=150, bbox_inches='tight')
        plt.close()

        return chart1_path, chart2_path, chart3_path

    def generate_pdf_report(self, results):
        """Generate a comprehensive PDF report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'retirement_report_{timestamp}.pdf'

        doc = SimpleDocTemplate(filename, pagesize=letter,
                               leftMargin=0.75*inch, rightMargin=0.75*inch,
                               topMargin=0.75*inch, bottomMargin=0.75*inch)

        story = []
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=30,
            alignment=TA_CENTER
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2ca02c'),
            spaceAfter=12,
            spaceBefore=12
        )

        # Title
        story.append(Paragraph('Retirement Planning Analysis Report', title_style))
        story.append(Paragraph(f'Generated: {datetime.now().strftime("%B %d, %Y")}', styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

        # Executive Summary
        story.append(Paragraph('Executive Summary', heading_style))

        accumulation_df = results['accumulation']
        retirement_df = results['retirement']

        success = results['success']
        status_color = colors.green if success else colors.red
        status_text = "✓ SUCCESS" if success else "⚠ WARNING"

        summary_data = [
            ['Status:', Paragraph(f'<font color="{status_color.hexval()}">{status_text}</font>', styles['Normal'])],
            ['Current Age:', f"{self.config['current_age']} years"],
            ['Retirement Age:', f"{self.config['retirement_age']} years"],
            ['Life Expectancy:', f"{self.config['life_expectancy']} years"],
            ['Years to Retirement:', f"{self.config['retirement_age'] - self.config['current_age']} years"],
            ['Balance at Retirement:', f"${results['retirement_balance']:,.2f}"],
            ['Final Balance:', f"${results['final_balance']:,.2f}"],
            ['Final Age:', f"{results['final_age']:.0f} years"],
        ]

        summary_table = RLTable(summary_data, colWidths=[2.5*inch, 3*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f4f8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.3*inch))

        # Account Information
        story.append(Paragraph('Account Information', heading_style))

        accounts = self.config['accounts']
        account_data = [['Account Name', 'Type', 'Starting Balance', 'Balance at Retirement']]

        for name, acc in accounts.items():
            acc_type = acc['type']
            type_map = {'pre_tax': 'Pre-Tax (401k/IRA)', 'roth': 'Roth', 'taxable': 'Taxable'}
            final_balance = accumulation_df.iloc[-1][f'{name}_balance']
            account_data.append([
                name.replace('_', ' ').title(),
                type_map.get(acc_type, acc_type),
                f"${acc['balance']:,.2f}",
                f"${final_balance:,.2f}"
            ])

        # Add total row
        total_start = sum(acc['balance'] for acc in accounts.values())
        account_data.append(['TOTAL', '', f"${total_start:,.2f}", f"${results['retirement_balance']:,.2f}"])

        account_table = RLTable(account_data, colWidths=[1.8*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        account_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ca02c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f4f8')),
            ('FONTNAME', (0, -1), (0, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
        ]))
        story.append(account_table)
        story.append(Spacer(1, 0.3*inch))

        # Key Metrics
        story.append(Paragraph('Key Financial Metrics', heading_style))

        metrics_data = [
            ['Total Contributions:', f"${results['total_contributions']:,.2f}"],
            ['Investment Gains:', f"${results['investment_gains']:,.2f}"],
            ['Total Accumulated:', f"${results['retirement_balance']:,.2f}"],
            ['Total Taxes Paid (Retirement):', f"${results['total_taxes_paid']:,.2f}"],
        ]

        if self.config.get('current_annual_income', 0) > 0:
            first_year_expense = retirement_df.iloc[1]['Annual_Expenses']
            replacement_ratio = (first_year_expense / self.config['current_annual_income']) * 100
            metrics_data.append(['Income Replacement Ratio:', f"{replacement_ratio:.1f}%"])

        metrics_table = RLTable(metrics_data, colWidths=[3*inch, 2.5*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f4f8')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(metrics_table)

        # Page break before charts
        story.append(PageBreak())

        # Generate and add charts
        story.append(Paragraph('Visual Analysis', heading_style))
        story.append(Spacer(1, 0.2*inch))

        chart1, chart2, chart3 = self._create_charts(accumulation_df, retirement_df)

        story.append(Image(chart1, width=6.5*inch, height=4*inch))
        story.append(Spacer(1, 0.2*inch))
        story.append(Image(chart2, width=6.5*inch, height=4*inch))

        # Page break before third chart
        story.append(PageBreak())
        story.append(Image(chart3, width=6.5*inch, height=4*inch))
        story.append(Spacer(1, 0.3*inch))

        # Accumulation Phase Summary - All Years
        story.append(PageBreak())
        story.append(Paragraph('Accumulation Phase - Year-by-Year Breakdown', heading_style))
        story.append(Spacer(1, 0.1*inch))

        acc_headers = ['Age', 'Total Balance']
        for name in accounts.keys():
            acc_headers.append(name.replace('_', ' ').title())

        acc_data = [acc_headers]

        # Add all years from accumulation dataframe
        for idx in range(len(accumulation_df)):
            row = accumulation_df.iloc[idx]
            row_data = [str(int(row['Age'])), f"${row['Total_Balance']:,.0f}"]
            for name in accounts.keys():
                row_data.append(f"${row[f'{name}_balance']:,.0f}")
            acc_data.append(row_data)

        col_width = 6.5*inch / len(acc_headers)
        acc_table = RLTable(acc_data, colWidths=[col_width] * len(acc_headers))
        acc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))
        story.append(acc_table)
        story.append(Spacer(1, 0.3*inch))

        # Retirement Phase Summary - All Years
        story.append(Paragraph('Retirement Phase - Year-by-Year Breakdown', heading_style))
        story.append(Spacer(1, 0.1*inch))

        ret_data = [['Age', 'Total Balance', 'Expenses', 'Social Security', 'Taxes', 'Net Withdrawal']]

        # Add all years from retirement dataframe
        for idx in range(len(retirement_df)):
            row = retirement_df.iloc[idx]
            ret_data.append([
                str(int(row['Age'])),
                f"${row['Total_Balance']:,.0f}",
                f"${row['Annual_Expenses']:,.0f}",
                f"${row['Social_Security']:,.0f}",
                f"${row['Taxes_Paid']:,.0f}",
                f"${row['Net_Withdrawal']:,.0f}"
            ])

        ret_table = RLTable(ret_data, colWidths=[0.8*inch, 1.3*inch, 1.2*inch, 1.3*inch, 0.9*inch, 1*inch])
        ret_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ff7f0e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))
        story.append(ret_table)

        # Footer
        story.append(Spacer(1, 0.5*inch))
        # Account Balances Over Time
        story.append(PageBreak())
        story.append(Paragraph('Account Balances During Retirement', heading_style))
        story.append(Spacer(1, 0.1*inch))

        # Get account names from config
        account_names = list(self.config['accounts'].keys())
        account_display_names = [name.replace('_', ' ').title() for name in account_names]

        # Build account balances table
        acct_data = [['Age'] + account_display_names + ['Total']]

        # Show every 5 years to keep table manageable
        for idx in range(0, len(retirement_df), max(1, len(retirement_df) // 20)):
            row = retirement_df.iloc[idx]
            row_data = [str(int(row['Age']))]

            # Add each account balance
            for account_name in account_names:
                balance = row.get(f'{account_name}_balance', 0)
                row_data.append(f"${balance:,.0f}")

            # Add total balance
            row_data.append(f"${row['Total_Balance']:,.0f}")
            acct_data.append(row_data)

        # Ensure last year is included
        if len(retirement_df) > 1:
            last_row = retirement_df.iloc[-1]
            if int(last_row['Age']) != int(acct_data[-1][0]):
                row_data = [str(int(last_row['Age']))]
                for account_name in account_names:
                    balance = last_row.get(f'{account_name}_balance', 0)
                    row_data.append(f"${balance:,.0f}")
                row_data.append(f"${last_row['Total_Balance']:,.0f}")
                acct_data.append(row_data)

        # Set column widths dynamically
        num_cols = len(account_names) + 2  # +2 for Age and Total columns
        col_width = 6.5 / num_cols * inch
        col_widths = [0.7*inch] + [col_width] * (num_cols - 1)

        acct_table = RLTable(acct_data, colWidths=col_widths)
        acct_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))
        story.append(acct_table)

        # Withdrawals by Account Over Time
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph('Withdrawals by Account During Retirement', heading_style))
        story.append(Spacer(1, 0.1*inch))

        wdr_data = [['Age'] + account_display_names + ['Withdrawls']]

        # Sample rows to keep table readable
        for idx in range(0, len(retirement_df), max(1, len(retirement_df) // 20)):
            row = retirement_df.iloc[idx]
            row_values = [str(int(row['Age']))]
            for account_name in account_names:
                val = row.get(f'{account_name}_withdrawal', 0)
                row_values.append(f"${val:,.0f}")
            row_values.append(f"${row['Gross_Withdrawal']:,.0f}")
            wdr_data.append(row_values)

        # Ensure last year included
        if len(retirement_df) > 1:
            last_row = retirement_df.iloc[-1]
            if int(last_row['Age']) != int(wdr_data[-1][0]):
                row_values = [str(int(last_row['Age']))]
                for account_name in account_names:
                    val = last_row.get(f'{account_name}_withdrawal', 0)
                    row_values.append(f"${val:,.0f}")
                row_values.append(f"${last_row['Gross_Withdrawal']:,.0f}")
                wdr_data.append(row_values)

        # Column widths similar to balances table
        num_cols_wdr = len(account_names) + 2
        col_width_wdr = 6.5 / num_cols_wdr * inch
        wdr_col_widths = [0.7*inch] + [col_width_wdr] * (num_cols_wdr - 1)

        wdr_table = RLTable(wdr_data, colWidths=wdr_col_widths)
        wdr_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ca02c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))
        story.append(wdr_table)

        # Footer
        story.append(Spacer(1, 0.3*inch))
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
                                     fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
        story.append(Paragraph(
            'This report is for planning purposes only and should not be considered financial advice. '
            'Actual results may vary based on market conditions and individual circumstances.',
            footer_style
        ))

        # Build PDF
        doc.build(story)

        return filename


def main():
    """Main entry point for the retirement planner."""
    console = Console()

    parser = argparse.ArgumentParser(description="Retirement planner")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration YAML file")
    args = parser.parse_args()
    try:
        planner = RetirementPlanner(args.config)
        planner.generate_full_projection()

    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] {args.config} file not found.")
        console.print("Please create a config file with your retirement parameters or pass --config path.")
        return 1
    except yaml.YAMLError as e:
        console.print("[bold red]Error:[/bold red] Failed to parse YAML configuration.")
        console.print(f"[dim]Details:[/dim] {e}")
        return 1
    except ValueError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interrupted by user[/bold yellow]")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
