
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
import os
from pytz import timezone as pytz_timezone


from datetime import datetime



# def transform_backend_payload(payload: dict,employee_id : str|None) -> dict:
#     # Format AWB number
#     raw_awb = payload.get("awb_no", "")
#     formatted_awb = f"{raw_awb[:3]}-{raw_awb[3:]}" if raw_awb else None

#     # Split xray_type into screening_method and other_screening
#     xray_type = payload.get("xray_type", "")
#     screening_method = xray_type[:3] if len(xray_type) >= 3 else "N.A"
#     other_chunks = [xray_type[i:i+3] for i in range(3, len(xray_type), 3)]
#     other_screening = ",".join(other_chunks) if other_chunks else "N.A"

#     # Date/time from xray_date_time
#     issued_date, issued_time = None, None
#     xray_dt = payload.get("xray_date_time")
#     if xray_dt:
#         dt = datetime.fromisoformat(xray_dt.replace("Z", "+00:00"))
#         issued_date = dt.strftime("%d-%b-%Y")
#         issued_time = dt.strftime("%H:%M")

#     # Serial number / doc_no
#     seq_num = payload.get("seq_num")
#     doc_no = seq_num 

#     return {
#         "regulated_entity_ids": ["IN/RA/000017-01", "IN/RA/000006-05"],
#         "awb_no": formatted_awb,
#         "contents": payload.get("name_of_goods"),
#         "consolidation": "Y",
#         "origin": "DEL",
#         "destination": payload.get("destination"),
#         "transit_points": "N/A",
#         "security_status": ["SPX", "SHR"],
#         "screening_method": screening_method,
#         "other_screening": other_screening,
#         "screener_name": payload.get("xray_user"),
#         "issued_date": issued_date,
#         "issued_time": issued_time,
#         "additional_info": payload.get("remarks"),
#         "doc_no": doc_no,
#         "employee_id" : employee_id
#     }


def transform_backend_payload(payload: dict, employee_id: str | None) -> dict:
    # Format AWB number
    raw_awb = payload.get("awb_no", "")
    formatted_awb = f"{raw_awb[:3]}-{raw_awb[3:]}" if raw_awb else None

    # Split xray_type into screening_method and other_screening
    xray_type = payload.get("xray_type", "") or ""
    screening_method = xray_type[:3] if len(xray_type) >= 3 else "N.A"
    other_chunks = [xray_type[i:i+3] for i in range(3, len(xray_type), 3)]
    other_screening = ",".join(other_chunks) if other_chunks else "N.A"

    # Date/time from xray_date_time
    issued_date, issued_time = None, None
    xray_dt = payload.get("xray_date_time")
    ist = pytz_timezone('Asia/Kolkata')
    
    if isinstance(xray_dt, datetime):
        # If datetime is timezone-aware, convert to IST
        if xray_dt.tzinfo is not None:
            dt_ist = xray_dt.astimezone(ist)
        else:
            # If naive, assume it's already IST
            dt_ist = ist.localize(xray_dt)
        
        issued_date = dt_ist.strftime("%d-%b-%Y")
        issued_time = dt_ist.strftime("%H:%M")
        
    elif isinstance(xray_dt, str):
        # Parse the ISO string and convert to IST
        dt = datetime.fromisoformat(xray_dt.replace("Z", "+00:00"))
        dt_ist = dt.astimezone(ist)
        issued_date = dt_ist.strftime("%d-%b-%Y")
        issued_time = dt_ist.strftime("%H:%M")
    # Serial number / doc_no
    seq_num = payload.get("seq_num")
    doc_no = seq_num if seq_num else str(payload.get("serial_no", "1")).zfill(7)

    return {
        "regulated_entity_ids": ["IN/RA/000017-01", "IN/RA/000006-05"],
        "awb_no": formatted_awb,
        "contents": payload.get("name_of_goods"),
        "consolidation": "Y",
        "origin": "DEL",
        "destination": payload.get("destination"),
        "transit_points": "N/A",
        "security_status": ["SPX", "SHR"],
        "screening_method": screening_method,
        "other_screening": other_screening,
        "screener_name": payload.get("xray_user"),
        "issued_date": issued_date,
        "issued_time": issued_time,
        "additional_info": payload.get("remarks"),
        "doc_no": doc_no,
        "employee_id": employee_id
    }


def generate_security_pdf(data: dict, output_dir: str = "static/pdfs") -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{data['awb_no']}.pdf"
    filepath = os.path.join(output_dir, filename)

    print('check ===================')

    print(data.get('employee_id'))

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    print(data)
    
    # Margins
    margin_left = 40
    margin_right = width - 40
    box_width = margin_right - margin_left
    
    # Starting Y position for header
    y_header = height - 50
    
    # Header section with borders
    header_height = 60
    # c.rect(margin_left, y_header - header_height, box_width, header_height)
    # Only vertical divider for logo section
    # logo_divider_x = margin_left + header_col2   # same position you used for column 3
    # c.line(logo_divider_x, y_header, logo_divider_x, y_header - header_height)

    
    # Vertical dividers in header (3 columns: Title | Restricted | Logo+Doc)
    header_col1 = box_width * 0.50  # Title section
    header_col2 = box_width * 0.70  # Restricted section
    
    # c.line(margin_left + header_col1, y_header, margin_left + header_col1, y_header - header_height)
    c.line(margin_left + header_col2, y_header, margin_left + header_col2, y_header - header_height-3)
    
    # Column 1: Appendix A and Title
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left + 15, y_header - 15, "Appendix A")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left + 8, y_header - 35, "CONSIGNMENT SECURITY DECLARATION")
    # c.drawString(margin_left + 8, y_header - 50, "")
    
    # Column 2: Restricted
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left + header_col1 + 40, y_header - 15, "Restricted")
    
    # Column 3: Document Number and Logo
    c.setFont("Helvetica-Bold", 15)
    doc_no = data.get('doc_no', '000001')
    c.drawString(margin_left + header_col2 + 85, y_header - 25, doc_no)
    
    # Logo
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, margin_left + header_col2 -15, y_header - 48, width=85, height=50, mask='auto', preserveAspectRatio=True)
    
    # "CARGO SERVICE CENTER" text below logo in grey
    c.setFillColorRGB(0.5, 0.5, 0.5)  # Grey color
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin_left + header_col2 + 8, y_header - 55, "DELHI CARGO SERVICE CENTER")
    c.setFillColorRGB(0, 0, 0)  # Back to black
    
    # Main form box starting position
    y = y_header - header_height - 3
    
    # Single large box for entire form
    form_box_height = 600
    c.rect(margin_left, y - form_box_height, box_width, form_box_height)
    
    # Internal padding
    pad = 8
    current_y = y - pad
    
    # Section 1: Regulated Entity & Consignment Identifier
    section_height = 52
    c.line(margin_left, current_y - section_height, margin_right, current_y - section_height)
    c.line(margin_left + box_width/2, current_y+8, margin_left + box_width/2, current_y - section_height)
    
    # Left: Regulated Entity
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 10, "Regulated Entity Category (RA, KC or AO) and Identifier")
    c.drawString(margin_left + pad, current_y - 22, "(of the regulated entity issuing the security status)")
    c.setFont("Helvetica-Bold", 10)
    # regulated_entities = data.get('regulated_entities', ['IN/RA/00007-01', 'IN/RA3/00006-05'])
    regulated_entities = data.get('regulated_entities', ['IN/RA/00007-03'])
    for i, entity in enumerate(regulated_entities):
        c.drawString(margin_left + pad+10, current_y - 38 - (i * 13), entity)
    
    # Right: Consignment Identifier
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + box_width/2 + pad, current_y - 10, "Unique consignment Identifier")
    c.drawString(margin_left + box_width/2 + pad, current_y - 22, "(If AWB format is nnn-nnnnnnnn)")
    c.setFont("Helvetica-Bold", 10)
    awb_no = data.get('awb_no', '098-76909744')
    # formatted_awb = f"{awb_no[:3]}-{awb_no[3:]}"
    
    c.drawString(margin_left + box_width/2 + pad + 10, current_y - 38, awb_no)
    
    current_y -= section_height
    
    # Section 2: Contents of Consignment (combined with Consolidation)
    section_height = 55
    c.line(margin_left, current_y - section_height, margin_right, current_y - section_height)
    
    # Horizontal divider between Contents and Consolidation
    contents_height = 30
    # c.line(margin_left, current_y - contents_height, margin_right, current_y - contents_height)
    
    # Contents subsection
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 10, "Contents of Consignment")
    c.setFont("Helvetica-Bold", 11)
    contents_text = data.get('contents', 'CONSOLIDATED GO')
    text_width = c.stringWidth(contents_text, "Helvetica-Bold", 12)
    c.drawString(margin_left + box_width/2 - text_width/2, current_y - 32, contents_text)
    
    # Consolidation subsection
    checkbox_size = 11
    checkbox_x = margin_left + pad + 5
    checkbox_y = current_y - contents_height - 18
    
    c.rect(checkbox_x, checkbox_y, checkbox_size, checkbox_size)

    # Keywords to check (case-insensitive) 
    keywords = ["consolidation", "consol", "cnsl"]

    if any(k in contents_text.lower() for k in keywords):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(checkbox_x + 2, checkbox_y + 1, "✔")
    
    c.setFont("Helvetica", 9)
    c.drawString(checkbox_x + checkbox_size + 7, checkbox_y + 2, "Consolidation")
    
    current_y -= section_height
    
    # Section 3: Origin, Destination, Transfer/Transit
    section_height = 58
    c.line(margin_left, current_y - section_height, margin_right, current_y - section_height)
    
    col_width = box_width / 3
    c.line(margin_left + col_width, current_y, margin_left + col_width, current_y - section_height)
    c.line(margin_left + 2*col_width, current_y, margin_left + 2*col_width, current_y - section_height)
    
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 12, "Origin")
    c.drawString(margin_left + col_width + pad, current_y - 12, "Destination")
    c.drawString(margin_left + 2*col_width + pad, current_y - 12, "Transfer/Transit Point (if known)")
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left + pad, current_y - 32, data.get('origin', 'DEL'))
    c.drawString(margin_left + col_width + pad, current_y - 32, data.get('destination', 'AMD'))
    c.drawString(margin_left + 2*col_width + pad, current_y - 32, data.get('transit_points', 'N/A'))
    
    current_y -= section_height
    
    # Section 4: Security Status
    section_height = 88
    c.line(margin_left, current_y - section_height, margin_right, current_y - section_height)
    
    status_col_width = 105
    c.line(margin_left + status_col_width, current_y, margin_left + status_col_width, current_y - section_height)
    
    # Header line for "Reasons for issuing Security Status"
    c.line(margin_left + status_col_width, current_y - 20, margin_right, current_y - 20)
    
    # Subdivide reasons section
    remaining_width = box_width - status_col_width
    sub_col_width = remaining_width / 3
    c.line(margin_left + status_col_width + sub_col_width, current_y - 19, margin_left + status_col_width + sub_col_width, current_y - section_height)
    c.line(margin_left + status_col_width + 2*sub_col_width, current_y - 19, margin_left + status_col_width + 2*sub_col_width, current_y - section_height)
    
    # Security Status
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 10, "Security Status")
    c.setFont("Helvetica-Bold", 11)
    security_status = data.get('security_status', ['SPX','SHR'])

    for i, status in enumerate(security_status):
        y_pos = current_y - 40 - (i * 20)
        # draw the status text on the left
        c.drawString(margin_left + pad, y_pos, status)

        # if status is SPX, draw a tick mark on the right side
        if status == "SPX":
            c.setFont("Helvetica-Bold", 12)
            # adjust X coordinate to the right side of the section
            c.drawString(margin_left + pad + 40, y_pos, "✔")
            c.setFont("Helvetica-Bold", 11)  # reset font for next iteration
    
    
    # Reasons header (centered)
    c.setFont("Helvetica", 9)
    header_text = "Reasons for issuing Security Status"
    header_width = c.stringWidth(header_text, "Helvetica", 9)
    c.drawString(margin_left + status_col_width + remaining_width/2 - header_width/2, current_y - 12, header_text)
    
    # Sub-headers
    c.drawString(margin_left + status_col_width + pad - 3, current_y - 30, "Received from (Codes)")
    c.drawString(margin_left + status_col_width + sub_col_width + pad - 3, current_y - 30, "Screening Method")
    c.drawString(margin_left + status_col_width + sub_col_width + pad - 3, current_y - 40, "(Codes)")
    c.drawString(margin_left + status_col_width + 2*sub_col_width + pad - 3, current_y - 30, "Grounds for Exemption (Codes)")
    
    # Screening method value
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left + status_col_width + 10   , current_y - 64, data.get('Received from (Codes)', 'N/A'))
    c.drawString(margin_left + status_col_width + sub_col_width + pad + 18, current_y - 64, data.get('screening_method', 'XRY'))
    c.drawString(margin_left + status_col_width + 2*sub_col_width + pad + 5 , current_y - 64, data.get('Grounds for Exemption (Codes)', 'N/A'))

    
    current_y -= section_height
    
    # Section 5: Other Screening Methods
    section_height = 70
    c.line(margin_left, current_y - section_height, margin_right, current_y - section_height)
    
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 15, "Other Screening Method(s) (if applicable)")
    c.setFont("Helvetica-Bold", 11)
    other_screening = data.get('other_screening', 'N/A')
    text_width = c.stringWidth(other_screening, "Helvetica-Bold", 11)
    c.drawString(margin_left + box_width/2 - text_width/2, current_y - 32, other_screening)
    
    current_y -= section_height
    
    # Section 6: Security Status issued by / issued on
    section_height = 90
    c.line(margin_left, current_y - section_height, margin_right, current_y - section_height)
    
    c.line(margin_left + box_width/2, current_y, margin_left + box_width/2, current_y - section_height)
    # c.line(margin_left + box_width/2, current_y - 16, margin_right, current_y - 16)
    
    # Left: Issued by
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 15, "Security Status issued by")
    c.drawString(margin_left + pad, current_y - 76, f"Name of the Person or Employee ID: {data.get('employee_id', '882908')}")
    c.drawString(margin_left + pad + 148, current_y - 80,"------------")
    
    # c.setFont("Helvetica-Bold", 10)
    # screener_name = data.get('screener_name', '9629 XRAY SCREENER 20')
    # name_width = c.stringWidth(screener_name, "Helvetica-Bold", 10)
    # c.drawString(margin_left + box_width/4 - name_width/2, current_y - 40, screener_name)
    
    # Right: Issued on
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + box_width/2 + pad, current_y - 15, "Security Status issued on")
    c.drawString(margin_left + box_width/2 + pad, current_y - 35, f"Date (dd/mm/yy): {data.get('issued_date', '18/12/25')}")
    c.drawString(margin_left + box_width/2 + pad + 70, current_y - 40,"-----------------")
    c.drawString(margin_left + box_width/2 + 165, current_y - 35, f"Time (tttt): {data.get('issued_time', '14:17')}")
    c.drawString(margin_left + box_width/2 + 165 + 45 , current_y - 40,"--------")

    current_y -= section_height
    
    # Section 7: Regulated Entity accepting
    section_height = 82
    c.line(margin_left, current_y - section_height, margin_right, current_y - section_height)
    
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 15, "Regulated Entity Category (RA, KC or AO) and Identifier (of the regulated entity who accepted the security status")
    c.drawString(margin_left + pad, current_y - 26, "given to consignment by another regulated entity)")

    c.setFont("Helvetica-Bold", 11)

    c.drawString(margin_left + box_width/2 - text_width/2, current_y - 32,"N/A")
    
    current_y -= section_height
    
    # Section 8: Additional Security Information (last section, no bottom line needed)
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + pad, current_y - 16, "Additional Security Information")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left + box_width/2 - text_width/2, current_y - 32,"N/A")

    # Footer warning (outside the box)
    footer_y = 50
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(margin_left, footer_y +2, "Warning :")
    c.setFont("Helvetica", 9)
    c.drawString(margin_left + 35, footer_y, " This document contains sensitive aviation security information which is regulated under rules 54 and ")
    c.drawString(margin_left, footer_y - 12, "55 of the Aircraft (Security) Rules, 2023. No part of this document may be disclosed to any person without a ")
    c.drawString(margin_left,footer_y - 24,'"need to know" as defined in NCASP.')
    
    c.save()
    return filepath