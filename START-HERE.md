# Aurora OS — Supermarket manager (Python edition)

Works **100% offline**. Your shop data lives in one folder on the computer
(`C:\Users\<you>\AppData\Roaming\AuroraOS`) and is never touched by updates.

## Try it now (any computer with Python 3.11+)
1. Unzip this folder.
2. Windows: double-click **run-dev.bat**. (Mac/Linux: `pip install -r requirements.txt` then `python run.py`.)
3. A window opens. The first time, a 2-step setup creates your shop and your owner login.
   Tick "add sample products" to practise on a ready-made shop.

## Turn it into a real Windows app
**Easiest (no setup on your side):** put this folder on GitHub (a private repo is fine) → *Actions* tab →
**Build Aurora OS for Windows** → *Run workflow*. After a few minutes download **AuroraOS-Windows**:
it contains `AuroraOS-Setup.exe` (a normal installer with Start-menu and desktop icons).

**Or on a Windows PC:** install Python 3.11+, double-click **build-windows.bat**.
The program appears in `dist\AuroraOS\AuroraOS.exe`. To make a one-file installer, install
*Inno Setup* and compile `build\installer.iss`.

## What's inside
- **Till (POS):** touch/click tiles, barcode scanner (just scan), weighed goods, split payments
  (cash/card/transfer/credit/points), hold & recall baskets, discounts, 80 mm receipts. Shortcuts: `/` search, `F4` hold, `F9` charge.
- **Safety:** prices are worked out by the program (the screen can't cheat), big discounts/refunds need a manager PIN,
  every action is in the activity log, 5 wrong passwords lock the account for 2 minutes.
- **Stock:** batches with expiry dates sold oldest-first, low-stock and expiry alerts, purchase orders with part deliveries,
  one-click "reorder what's low", stock counts that show shrinkage, CSV import/export.
- **Money:** cash-drawer shifts (blind count), VAT (7.5% default, exemptions per product), expenses, real profit,
  customer credit with limits, loyalty points.
- **Reports:** sales, profit, top products, categories, cashiers, payment mix, slow movers, stock value.
- **Backups:** automatic daily (+ a second copy to a USB folder), restore with one click.
- Dark **northern-lights** theme (default) and a clean light theme — switch in the sidebar.

## Developers
`python -m pytest tests -q` runs 12 end-to-end tests. Code map: `aurora/services` (stock, sales, backup),
`aurora/routes` (pages + JSON API), `aurora/templates`, `aurora/static`.
Money is stored as whole kobo; every change that touches stock runs in one database transaction.
