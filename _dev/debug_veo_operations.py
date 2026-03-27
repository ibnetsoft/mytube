
import sys
import inspect
from google import genai

print(f"Python executable: {sys.executable}")

try:
    print("Inspecting google.genai.Client.operations.get...")
    # We can't instantiate Client without API key easily if it checks strictly, 
    # but we can inspect the class method if it's not dynamic.
    
    # Check if we can inspect the class directly
    if hasattr(genai, 'Client'):
        client_cls = genai.Client
        if hasattr(client_cls, 'operations'):
            # operations might be a property or a class
            # Let's try to see what type it is.
            print(f"Client.operations type: {type(client_cls.operations)}")
            
        # If operations is initialized in __init__, we need an instance.
        # Let's try to mock or use a dummy key.
        try:
            client = genai.Client(api_key="DUMMY_KEY")
            print("Successfully created Client with dummy key.")
            
            if hasattr(client, 'operations'):
                ops = client.operations
                print(f"client.operations: {ops}")
                if hasattr(ops, 'get'):
                    print(f"client.operations.get: {ops.get}")
                    sig = inspect.signature(ops.get)
                    print(f"Signature of client.operations.get: {sig}")
                    print(f"Docstring: {ops.get.__doc__}")
                else:
                    print("client.operations does not have 'get' method.")
            else:
                print("client instance has no 'operations' attribute.")
                
        except Exception as e:
            print(f"Failed to instantiate Client: {e}")

except ImportError as e:
    print(f"Failed to import google.genai: {e}")
