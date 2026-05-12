import streamlit.components.v1 as components
import base64
import os
import sys

_component_func = components.declare_component("file_uploader", path=os.path.dirname(__file__))

def file_uploader(key=None):
    result = _component_func(key=key)
    if result and isinstance(result, dict) and 'data' in result and 'name' in result:
        raw = base64.b64decode(result['data'])
        filepath = os.path.join('/app/data', result['name'])
        os.makedirs('/app/data', exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(raw)
        sys.path.insert(0, '/app')
        from data_collector import import_excel_data
        try:
            count = import_excel_data(filepath)
            return True, f"Imported {count} records from {result['name']}"
        except Exception as e:
            return False, f"Import error: {e}"
    return None, None
