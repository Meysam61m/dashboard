"""ساخت صفحه چاپی یک‌صفحه‌ای A4 مطابق نمونه 405001.pdf."""
import base64
import html as html_mod
from pathlib import Path

from . import config

E = html_mod.escape


def _money(v) -> str:
    try:
        return f"{float(v or 0):,.0f}"
    except (TypeError, ValueError):
        return "0"


def _logo_data_uri() -> str:
    p = config.LOGO_PATH
    if p.exists():
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
    return ""


CSS = """
@page { size: A4 portrait; margin: 6mm; }
* { box-sizing: border-box; }
body { font-family: Vazirmatn, Tahoma, Arial, sans-serif; direction: rtl;
       margin: 0; color: #000; background: #fff; }
.page { width: 196mm; font-size: 8pt; line-height: 1.35; position: relative; }
table { width: 100%; border-collapse: collapse; }
.hd td { border: none; vertical-align: top; padding: 1px 3px; }
.org { text-align: right; font-size: 8.5pt; font-weight: bold; }
.title { text-align: center; font-size: 13pt; font-weight: bold; }
.branch { text-align: center; font-size: 11pt; font-weight: bold; }
.logo { text-align: center; }
.logo img { height: 20mm; }
.meta { text-align: left; font-size: 8pt; }
.items th, .items td { border: 1px solid #000; padding: 2px 3px; text-align: center; }
.items th { background: #eee; font-size: 8pt; }
.items td.t { text-align: right; }
.items td.n { text-align: left; direction: ltr; }
.total td { background: #f3f3f3; font-weight: bold; }
.note { margin: 2mm 0; font-size: 8.5pt; }
.sig-left { text-align: left; }
.box { border: 1px solid #000; padding: 1.5mm 2mm; height: 100%; }
.box h4 { margin: 0 0 1mm 0; font-size: 8.5pt; text-align: right; }
.boxes td { width: 50%; vertical-align: top; padding: 1mm; border: none; }
.sigrow { margin-top: 2.5mm; display: flex; justify-content: space-around; font-size: 7.5pt; }
.sig { text-align: center; min-width: 26mm; }
.sig .line { border-bottom: 1px solid #000; margin-bottom: 1mm; height: 6mm; }
.dots { letter-spacing: 1px; }
.tanakhah { border: 1.5px solid #000; padding: 2mm; width: 72mm; margin-right: auto; font-size: 8pt; }
.tanakhah .line { border-bottom: 1px solid #000; height: 7mm; margin-top: 1.5mm; }
.foot { margin-top: 2mm; }
.foot td { border: 1px solid #000; font-size: 7.5pt; padding: 1.5mm 2mm; text-align: right; }
.foot td b { display: block; font-size: 7pt; }
.draft-mark { position: absolute; top: 45%; right: 20%; transform: rotate(-18deg);
              font-size: 42pt; color: rgba(180,0,0,0.28); font-weight: bold; }
.dotsline { border-bottom: 1px dotted #000; display: inline-block; }
"""


def build_print_html(doc: dict, tanakhah: dict, settings: dict) -> str:
    """doc: خروجی services.get_document + باید شامل items/totals باشد."""
    logo = _logo_data_uri()
    logo_html = f'<img src="{logo}" alt="logo">' if logo else ""
    draft = doc["status"] != "final"
    t = doc["totals"]

    rows_html = ""
    for it in doc["items"]:
        rows_html += (
            f"<tr><td>{it['row_no']}</td><td>{E(it['item_date'] or '')}</td>"
            f"<td class='t'>{E(it['title'])}</td>"
            f"<td class='n'>{_money(it['insurance'])}</td>"
            f"<td class='n'>{_money(it['tax'])}</td>"
            f"<td class='n'>{_money(it['amount'])}</td></tr>"
        )
    # ردیف‌های خالی تا ۱۵ (برای جلوگیری از دست‌نویسی روی چاپ، فقط در صورت درخواست — پیش‌فرض: فقط ردیف‌های پرشده)

    total_row = (
        f"<tr class='total'><td colspan='3'>جمع کل</td>"
        f"<td class='n'>{_money(t['insurance'])}</td>"
        f"<td class='n'>{_money(t['tax'])}</td>"
        f"<td class='n'>{_money(t['amount'])}</td></tr>"
    )
    # نکته: در نمونه، جمع کل «مبلغ» ستون انتهایی است؛ جمع کل کلی (همه ستون‌ها) در صورت نیاز:
    grand = _money(t["total"])

    num = E(doc["doc_number"] or "—")
    doc_date = E(doc["doc_date"])
    status_label = {"draft": "پیش‌نویس", "final": "", "void": "باطل‌شده"}[doc["status"]]
    void_note = ""
    if doc["status"] == "void":
        void_note = f"<div style='text-align:center;color:#a00;font-weight:bold'>این سند باطل شده است — دلیل: {E(doc.get('void_reason') or '')}</div>"

    last_dep = E(tanakhah.get("last_date") or "—")
    balance = _money(tanakhah.get("balance", 0))

    html_doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>سند {num}</title><style>{CSS}</style></head>
<body><div class="page">
{'<div class="draft-mark">پیش‌نویس</div>' if draft and doc['status'] == 'draft' else ''}
{void_note}
<table class="hd"><tr>
  <td class="org">{E(settings.get('company_name', ''))}<br>{E(settings.get('complex_name', ''))}
      <br><span style="font-size:7.5pt;font-weight:normal">ش ملی: {E(settings.get('national_id', ''))}
      &nbsp;&nbsp; کد اقتصادی: {E(settings.get('economic_code', ''))}</span></td>
  <td>
    <div class="logo">{logo_html}</div>
    <div class="branch">{E(doc.get('branch_name', ''))}</div>
    <div class="title">{E(settings.get('doc_title', ''))}{(' — ' + status_label) if status_label else ''}</div>
  </td>
  <td class="meta">تاریخ: {doc_date}<br>شماره سند: {num}
      <br><br>تاریخ بازنگری: {E(settings.get('doc_control_date', ''))}
      &nbsp; {E(settings.get('doc_control', ''))}</td>
</tr></table>

<table class="items">
  <tr><th rowspan="2" style="width:7%">ردیف</th><th rowspan="2" style="width:13%">تاریخ</th>
      <th rowspan="2" style="width:37%">شرح هزینه</th><th colspan="3" style="width:43%">مبلغ به (ریال)</th></tr>
  <tr><th style="width:14%">بیمه</th><th style="width:14%">مالیات</th><th style="width:15%">مبلغ</th></tr>
  {rows_html}
  {total_row}
</table>

<div class="note">{E(settings.get('standard_text', ''))}
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <span class="sig-left">امضاء كارپرداز</span></div>

<table class="boxes"><tr>
 <td><div class="box"><h4>درخواست صدور چک تنخواه</h4>
   <div>احتراماً خواهشمند است در خصوص صدور چک تنخواه شماره
   <span class="dotsline" style="width:22mm"></span> در وجه اینجانب
   <span class="dotsline" style="width:30mm"></span> دستور اقدام مقتضی صادر فرمایند.</div>
   <div class="sigrow">
     <div class="sig"><div class="line"></div>تاریخ: </div>
     <div class="sig"><div class="line"></div>امضاء كارپرداز</div>
   </div></div></td>
 <td><div class="box"><h4>بررسی امور مالی</h4>
   <div>اسناد و مدارک مربوطه شامل تعداد <span class="dotsline" style="width:12mm"></span>
   برگ به مبلغ کل <span class="dotsline" style="width:18mm"></span> ریال بررسی گردید.</div>
   <div>شرح بررسی <span class="dotsline" style="width:40mm"></span></div>
   <div class="sigrow">
     <div class="sig"><div class="line"></div>کارشناس حسابداری<br>تاریخ: </div>
     <div class="sig"><div class="line"></div>مسئول حسابداری<br>تاریخ: </div>
     <div class="sig"><div class="line"></div>مسئول امور کارکنان<br>تاریخ: </div>
   </div></div></td>
</tr>
<tr>
 <td><div class="box"><h4>دستور صدور چک</h4>
   <div>امور مالی با پرداخت مبلغ <span class="dotsline" style="width:22mm"></span>
   ریال موافقت می‌شود.</div>
   <div class="sigrow">
     <div class="sig"><div class="line"></div>مدیریت<br>تاریخ: </div>
     <div class="sig"><div class="line"></div>رئیس مالی و اداری<br>تاریخ: </div>
     <div class="sig"><div class="line"></div>اداری مالی<br>تاریخ: </div>
   </div></div></td>
 <td><div class="box"><h4>صدور و تحویل چک</h4>
   <div>چک شماره <span class="dotsline" style="width:16mm"></span> به مبلغ
   <span class="dotsline" style="width:18mm"></span> ریال بتاریخ
   <span class="dotsline" style="width:14mm"></span> جاری
   <span class="dotsline" style="width:14mm"></span> بانک
   <span class="dotsline" style="width:12mm"></span></div>
   <div>در وجه <span class="dotsline" style="width:40mm"></span> صادر و تحویل گردید.</div>
   <div class="sigrow">
     <div class="sig"><div class="line"></div>دریافت کننده<br>تاریخ: </div>
     <div class="sig"><div class="line"></div>امور مالی<br>تاریخ: </div>
   </div></div></td>
</tr></table>

<table style="border:none;margin-top:2mm"><tr>
 <td style="border:none;padding:0">
   <div class="tanakhah">
     <b>آخرین واریز تنخواه:</b> {last_dep} &nbsp;&nbsp; <b>مانده تنخواه:</b> {balance} ریال
     <div class="line"></div>
     <div style="text-align:center;font-size:7.5pt">امضاء</div>
   </div>
 </td>
</tr></table>

<table class="foot"><tr>
  <td><b>شماره سند حسابداری</b></td>
  <td><b>معاملات فصلی</b></td>
  <td><b>نمره اسناد</b></td>
  <td><b>اسکن اسناد مالی</b></td>
  <td style="width:34%"><b>توضیحات قابل بررسی</b></td>
</tr></table>

<div style="text-align:left;font-size:6.5pt;color:#666;margin-top:1mm">
  جمع کل سند (مبلغ + بیمه + مالیات): {grand} ریال &nbsp;|&nbsp; چاپ‌شده: {doc.get('print_count', 0)}
</div>
</div></body></html>"""
    return html_doc


def build_file(doc: dict, tanakhah: dict, settings: dict) -> str:
    return build_print_html(doc, tanakhah, settings)
