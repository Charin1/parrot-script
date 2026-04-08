from typing import Any

from fpdf import FPDF

class DocumentPDF(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 14)
        self.set_text_color(11, 114, 133) # Brand accent color
        self.cell(0, 10, "Parrot Script", border=False, new_x="LMARGIN", new_y="NEXT", align="L")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def generate_transcript_pdf(title: str, segments: list[dict[str, Any]]) -> bytes:
    pdf = DocumentPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(31, 36, 33)
    pdf.multi_cell(0, 10, f"Meeting Transcript: {title}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    # Content
    for seg in segments:
        speaker = seg.get("display_name") or seg.get("speaker", "Unknown")
        text = seg.get("text", "").strip()
        start = seg.get("start_time", 0.0)
        
        # Speaker Name & Timestamp
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(11, 114, 133)
        pdf.cell(0, 6, f"[{start:.1f}s] {speaker}:", new_x="LMARGIN", new_y="NEXT")
        
        # Speech Text
        pdf.set_font("helvetica", "", 11)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        
    return pdf.output(dest="S")

def generate_summary_pdf(title: str, summary_content: str) -> bytes:
    pdf = DocumentPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(31, 36, 33)
    pdf.multi_cell(0, 10, f"Meeting Summary: {title}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    # Content body (Basic parsing for markdown bold/bullets is complex in raw FPDF, 
    # so we will render it as a clean multi_cell with a unicode compliant font ideally, 
    # but helvetica works for basic ascii markdown)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(50, 50, 50)
    
    # Simple cleanup to make markdown readable in raw text
    text = summary_content.replace("**", "")
    text = text.replace("#", "")
    
    pdf.multi_cell(0, 6, text.strip(), new_x="LMARGIN", new_y="NEXT")
    
    return pdf.output(dest="S")
