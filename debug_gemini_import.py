
import sys
import os

print(f"Python executable: {sys.executable}")

try:
    import google.generativeai as genai_old
    print(f"Successfully imported google.generativeai. Version: {genai_old.__version__}")
    print(f"Attributes: {dir(genai_old)}")
except ImportError as e:
    print(f"Failed to import google.generativeai: {e}")

try:
    from google import genai
    print(f"Successfully imported google.genai")
    print(f"Attributes of google.genai: {dir(genai)}")
    
    if hasattr(genai, 'Client'):
        print("genai.Client exists.")
        try:
             # Do not perform actual auth, just inspect class
             print(f"Client attributes: {dir(genai.Client)}")
        except:
             pass
    else:
        print("genai.Client DOES NOT exist.")

except ImportError as e:
    print(f"Failed to import google.genai: {e}")
