import fitz  # PyMuPDF
import re
from decimal import Decimal, ROUND_HALF_UP

def clean_num(text):
    """Strips currency symbols and commas to convert string to float."""
    try:
        return float(text.replace('$', '').replace(',', '').strip())
    except ValueError:
        return None

def int_to_rgb(color_int):
    """Converts PyMuPDF's integer color codes to RGB tuples for injection."""
    b = color_int & 255
    g = (color_int >> 8) & 255
    r = (color_int >> 16) & 255
    return (r / 255.0, g / 255.0, b / 255.0)

def process_flawless_invoice(input_pdf_path, output_pdf_path):
    doc = fitz.open(input_pdf_path)
    
    for page in doc:
        text_dict = page.get_text("dict")
        spans = []
        
        for block in text_dict.get("blocks", []):
            if block.get("type") == 0:  
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        spans.append(span)
                        
        c_shipped = c_price = c_ext = None
        for s in spans:
            text = s['text'].strip()
            x_center = (s['bbox'][0] + s['bbox'][2]) / 2
            if text == "SHIPPED": c_shipped = x_center
            elif text == "PRICE": c_price = x_center
            elif text == "EXTENSION": c_ext = x_center
            
        if None in (c_shipped, c_price, c_ext):
            continue  
            
        rows = {}
        for s in spans:
            y_baseline = round(s['origin'][1])
            if y_baseline not in rows:
                rows[y_baseline] = []
            rows[y_baseline].append(s)
            
        replacements = []
        old_invoice_total = Decimal('0.00')
        new_invoice_total = Decimal('0.00')
        
        for y, row_spans in rows.items():
            qty_s = price_s = ext_s = None
            
            for s in row_spans:
                xc = (s['bbox'][0] + s['bbox'][2]) / 2
                if abs(xc - c_shipped) < 25 and s['text'].strip().isdigit():
                    qty_s = s
                elif abs(xc - c_price) < 25 and clean_num(s['text']) is not None:
                    price_s = s
                elif abs(xc - c_ext) < 35 and clean_num(s['text']) is not None:
                    ext_s = s
                    
            if qty_s and price_s and ext_s:
                qty = Decimal(qty_s['text'].strip())
                old_price = Decimal(str(clean_num(price_s['text'])))
                old_ext = Decimal(str(clean_num(ext_s['text'])))
                
                old_invoice_total += old_ext
                
                # Strict Financial Math Logic: Price / .80 * QTY
                factor = Decimal('0.80')
                new_price_raw = old_price / factor
                
                # Force round half up to exactly two decimal places
                new_price = new_price_raw.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                new_ext_raw = new_price * qty
                new_ext = new_ext_raw.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                
                new_invoice_total += new_ext
                
                replacements.append({
                    'span': price_s,
                    'new_text': f"${new_price:,.2f}" if '$' in price_s['text'] else f"{new_price:,.2f}"
                })
                replacements.append({
                    'span': ext_s,
                    'new_text': f"${new_ext:,.2f}" if '$' in ext_s['text'] else f"{new_ext:,.2f}"
                })

        if old_invoice_total > 0:
            for s in spans:
                val = clean_num(s['text'])
                if val is not None and abs(Decimal(str(val)) - old_invoice_total) < Decimal('0.01'):
                    
                    if ',' not in s['text']:
                        new_text_fmt = f"{new_invoice_total:.2f}"
                    else:
                        new_text_fmt = f"{new_invoice_total:,.2f}"
                        
                    if '$' in s['text']:
                        new_text_fmt = f"${new_text_fmt}"
                        
                    replacements.append({
                        'span': s,
                        'new_text': new_text_fmt
                    })
                    
        for rep in replacements:
            page.add_redact_annot(rep['span']['bbox'])
            
        page.apply_redactions(images=0, graphics=0)
        
        for rep in replacements:
            span = rep['span']
            new_text = rep['new_text']
            
            original_fontsize = span['size']
            original_color = int_to_rgb(span['color'])
            baseline_y = span['origin'][1]
            
            text_length = fitz.get_text_length(new_text, fontname="helv", fontsize=original_fontsize)
            aligned_x = span['bbox'][2] - text_length
            
            page.insert_text(
                (aligned_x, baseline_y),
                new_text,
                fontname="helv",
                fontsize=original_fontsize,
                color=original_color
            )

    doc.save(output_pdf_path)
    doc.close()
    print(f"Flawless generation complete! Saved to {output_pdf_path}")

if __name__ == "__main__":
    import os
    import sys
    
    INPUT_FILE = "input.pdf"
    OUTPUT_FILE = "output.pdf"
    
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Please upload a file named 'input.pdf'.")
        sys.exit(1)
        
    process_flawless_invoice(INPUT_FILE, OUTPUT_FILE)