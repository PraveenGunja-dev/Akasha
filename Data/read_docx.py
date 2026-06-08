import zipfile
import xml.etree.ElementTree as ET
import sys

def read_docx(file_path):
    try:
        with zipfile.ZipFile(file_path) as docx:
            xml_content = docx.read('word/document.xml')
            
        tree = ET.fromstring(xml_content)
        
        # Namespaces are commonly used in docx xml
        namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        
        paragraphs = []
        for paragraph in tree.findall('.//w:p', namespaces):
            texts = [node.text for node in paragraph.findall('.//w:t', namespaces) if node.text]
            if texts:
                paragraphs.append(''.join(texts))
        
        return '\n'.join(paragraphs)
    except Exception as e:
        return f"Error reading docx: {e}"

if __name__ == '__main__':
    text = read_docx(r"d:\Akasha_Platform\Data\Akasha SOW.docx")
    with open(r"d:\Akasha_Platform\Data\SOW_extracted.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("Done")
