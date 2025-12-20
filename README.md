# Retirement Planner

A Python-based retirement planning tool that projects your savings growth and analyzes whether you'll have enough money to last through retirement, with support for multiple account types and tax-aware withdrawal strategies.

## Features

- **Multi-Account Support**: Track Traditional 401(k), Roth IRA, and Taxable accounts separately
- **Tax-Aware Withdrawals**: Automatically applies correct tax treatment for each account type
- **Smart Withdrawal Strategy**: Configurable order to minimize tax burden (e.g., taxable → traditional → Roth)
- **Accumulation Phase Analysis**: Projects savings growth for each account until retirement
- **Retirement Phase Analysis**: Models tax-efficient spending and balance throughout retirement
- **Comprehensive Reporting**: Generates detailed year-by-year CSV reports with account breakdowns
- **PDF Reports**: Professional PDF reports with charts, tables, and complete analysis
- **Visual Charts**: Matplotlib-generated charts showing balance trends and account drawdown
- **Beautiful Console Output**: Rich-formatted terminal output with tables and charts
- **Configurable Inputs**: All parameters in an easy-to-edit YAML config file
- **Pandas Integration**: Uses pandas DataFrames for efficient calculations and reporting

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` to set your personal retirement parameters:

### Personal Information
- `current_age`: Your current age
- `retirement_age`: Age you plan to retire
- `life_expectancy`: Expected lifespan
- `current_annual_income`: Current annual income (for replacement ratio calculation)

### Tax Rates
- `current_tax_rate`: Current marginal tax rate (e.g., 0.24 = 24%)
- `retirement_tax_rate`: Expected effective tax rate in retirement (e.g., 0.15 = 15%)
- `capital_gains_rate`: Long-term capital gains tax rate (e.g., 0.15 = 15%)

### Accounts
Define multiple retirement accounts with different tax treatments and optional per-account interest rates:

```yaml
accounts:
  traditional_401k:
    balance: 30000              # Current balance
    annual_contribution: 10000  # Annual contribution
    contribution_limit: 23000   # IRS limit (null for no limit)
    type: pre_tax              # Account type

  roth_ira:
    balance: 15000
    annual_contribution: 3000
    contribution_limit: 7000
    type: roth                 # Tax-free withdrawals

  taxable:
    balance: 5000
    annual_contribution: 2000
    contribution_limit: null
    type: taxable              # Capital gains tax

  cash:
    balance: 3000
    annual_contribution: 0
    contribution_limit: null
    interest_rate: 0.02        # Optional per-account interest rate (cash defaults to 0.0 if omitted)
    type: cash                  # Withdrawals treated as tax-free principal in this model
```

**Account Types:**
- `pre_tax`: Traditional 401(k)/IRA - contributions reduce taxable income, withdrawals taxed as ordinary income
- `roth`: Roth 401(k)/IRA - contributions from after-tax money, withdrawals tax-free
- `taxable`: Brokerage accounts - capital gains tax applies
- `cash`: Cash-like holdings - uses `interest_rate` if provided; withdrawals modeled as tax-free principal

### Investment Returns
- `expected_return_rate`: Expected annual investment return (e.g., 0.07 = 7%). Used for all accounts unless an account specifies its own `interest_rate`.
- `inflation_rate`: Expected annual inflation (e.g., 0.03 = 3%)
- `contribution_growth_rate`: Annual increase in contributions (e.g., 0.03 = 3%)

Per-account override:
- Any account may include `interest_rate` to override the global `expected_return_rate`.
- If an account has `type: cash` and no `interest_rate`, it defaults to 0.0%.

### Retirement Expenses
- `annual_retirement_expenses`: Expected annual expenses in today's dollars
- `expense_growth_rate`: Annual increase in expenses during retirement

### Withdrawal Strategy
- `withdrawal_order`: List of accounts in order to withdraw from (e.g., `[taxable, traditional_401k, roth_ira]`). You can include `cash` anywhere in the order to match your spending preference.

### Social Security / Pension
- `annual_social_security`: Expected annual social security in today's dollars
- `social_security_start_age`: Age when social security benefits begin

### Other Income
- `other_annual_income`: Any other expected annual income during retirement

## Usage

Run the retirement planner (defaults to `config.yaml`):

```bash
python retirement_planner.py --config config.yaml
```

### Cleaning generated PDF reports

Use the provided script to remove timestamped PDF reports (`retirement_report_*.pdf`):

```bash
chmod +x clean_reports.sh
./clean_reports.sh --dry-run         # show what would be deleted
./clean_reports.sh                   # delete in current directory
./clean_reports.sh --path /tmp/reports  # delete in another directory
```

Set `NO_CONFIRM=1` to skip the confirmation prompt:

```bash
NO_CONFIRM=1 ./clean_reports.sh
```

### Make targets

Convenient Makefile commands are included:

```bash
make install         # install dependencies
make run             # run planner with sample config.yaml
make clean-dry       # preview deletion of retirement_report_*.pdf
make clean           # delete retirement_report_*.pdf in repo root
```

To use your private configuration, pass its path:

```bash
python retirement_planner.py --config config_jgu.yaml
```

This repo includes a public-safe sample `config.yaml`. Customize it or create your own file to avoid committing sensitive data.

The program will:
1. Load your configuration from `config.yaml`
2. Calculate accumulation phase (savings growth until retirement)
3. Calculate retirement phase (spending through retirement)
4. Display a comprehensive analysis in the terminal
5. Generate detailed reports:
   - `accumulation_phase.csv`: Year-by-year savings growth data
   - `retirement_phase.csv`: Year-by-year retirement spending data
   - `retirement_report_YYYYMMDD_HHMMSS.pdf`: Professional PDF report with charts and analysis

## Example Output

```
================================================================================
RETIREMENT PLANNER - FULL PROJECTION
================================================================================

--- ACCUMULATION PHASE (Saving for Retirement) ---

Years until retirement: 35
Starting balance: $50,000.00
Initial annual contribution: $15,000.00

✓ Projected balance at retirement (age 65): $2,847,421.18

--- RETIREMENT PHASE (Spending Years) ---

Years in retirement: 25
Starting retirement balance: $2,847,421.18
Initial annual expenses: $113,796.88

✓ Final balance at age 90: $1,245,328.45

================================================================================
RETIREMENT READINESS ANALYSIS
================================================================================

✓ SUCCESS: You are projected to have $1,245,328.45 remaining at age 90
  Your retirement savings should last through your expected lifetime.
```

## Understanding the Results

- **SUCCESS**: Your savings are projected to last through your expected lifetime
- **WARNING**: Your funds may run out before life expectancy - consider adjusting parameters

### Account-Level Tracking

The program tracks each account separately during:
- **Accumulation**: Shows growth of each account with contribution limits enforced
- **Retirement**: Displays which accounts are being drawn down and in what order

### Key Metrics Explained

- **Total contributions**: Sum of all contributions across all accounts during working years
- **Investment gains**: Growth from investment returns across all accounts
- **Total taxes paid (retirement)**: Cumulative taxes on withdrawals based on account type
- **Income replacement ratio**: Retirement expenses as % of pre-retirement income
- **Net withdrawal**: After-tax amount withdrawn to cover expenses

### Tax Treatment by Account Type

- **Pre-tax (Traditional 401k/IRA)**: Withdrawals taxed at `retirement_tax_rate`
- **Roth**: Withdrawals are tax-free
- **Taxable**: Capital gains tax applied (assumes 50% cost basis)

### Withdrawal Strategy

The program withdraws in the order specified in `withdrawal_order` to minimize taxes:
1. **Taxable first**: Lower tax rate (capital gains) and allows tax-deferred accounts to grow
2. **Traditional next**: Required distributions and ordinary income tax
3. **Roth last**: Preserve tax-free growth as long as possible

## PDF Report

The program automatically generates a comprehensive PDF report that includes:

### Report Contents
- **Executive Summary**: Key statistics and retirement readiness status
- **Account Information**: Starting and ending balances for each account
- **Key Financial Metrics**: Contributions, gains, taxes, and replacement ratio
- **Visual Charts**:
  - Account growth during accumulation phase
  - Balance vs. expenses during retirement
  - Account drawdown visualization (stacked area chart)
- **Detailed Tables**: Selected years from both accumulation and retirement phases
  - Account balances table during retirement includes all configured accounts (e.g., cash, taxable, traditional, Roth)
  - Withdrawals by account during retirement (year-by-year gross withdrawals per account)
- **Professional Layout**: Color-coded sections and formatted tables

The PDF report is saved with a timestamp (e.g., `retirement_report_20251213_100451.pdf`) so you can track different scenarios and plan versions.

## Adjusting Your Plan

If the analysis shows your funds may run out:
- Increase annual contributions (within account limits)
- Work longer (increase retirement age)
- Reduce retirement expenses
- Consider more aggressive investment strategy (higher expected returns)
- Maximize social security by delaying benefits
- Optimize withdrawal order to reduce taxes
- Increase Roth conversions during lower-income years

## License

This is a personal financial planning tool. Use at your own discretion. Results are projections based on assumptions and should not be considered financial advice.
