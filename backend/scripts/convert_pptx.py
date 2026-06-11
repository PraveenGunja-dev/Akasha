import sys
import os

try:
    import win32com.client
    
    input_file = r"d:\Akasha_Platform\frontend\public\AGEL AKASHA Cross Functional Intelligence.pptx"
    output_file = r"d:\Akasha_Platform\frontend\public\AGEL_AKASHA_Presentation.pdf"
    
    if os.path.exists(output_file):
        os.remove(output_file)
        
    powerpoint = win32com.client.Dispatch("Powerpoint.Application")
    deck = powerpoint.Presentations.Open(input_file, WithWindow=False)
    deck.SaveAs(output_file, 32) # 32 is the format code for PDF
    deck.Close()
    powerpoint.Quit()
    print("Successfully converted PPTX to PDF!")
except Exception as e:
    print(f"Error converting: {e}")
