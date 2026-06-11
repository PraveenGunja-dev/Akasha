import fitz
import os

pdf_path = r"d:\Akasha_Platform\frontend\public\AGEL_AKASHA_Presentation.pdf"
output_dir = r"d:\Akasha_Platform\frontend\public\slides"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

doc = fitz.open(pdf_path)
for i in range(len(doc)):
    page = doc.load_page(i)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for better resolution
    pix.save(f"{output_dir}/slide_{i+1}.png")

print(f"Extracted {len(doc)} slides to {output_dir}")
