import os
import json
import random
import re
import tempfile
import time
import uuid
from datetime import datetime
from typing import List

import pandas as pd


def get_data_file_path(filename: str) -> str:
    """Resolve the absolute path to a file in the package's ``data`` directory.

    Resolves the path relative to this package instead of using the deprecated
    ``pkg_resources``. This works across Python versions (3.8+) and for both
    regular and editable (``pip install -e``) installs, since the ``data``
    directory always sits alongside the ``symbols`` package.

    Parameters
    ----------
    filename : str
        The name of the file inside ``tradingview_scraper/data`` (e.g.
        ``'indicators.txt'``).

    Returns
    -------
    str
        The absolute path to the requested data file.
    """
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(package_root, 'data', filename)


def ensure_export_directory(path='/export'):
    """Check if the export directory exists, and create it if it does not.

    Parameters
    ----------
    path : str, optional
        The path to the export directory. Defaults to '/export'.

    Raises
    ------
    Exception
        If there is an error creating the directory.
    """
    if not os.path.exists(path):
        try:
            os.makedirs(path, exist_ok=True)
            print(f"[INFO] Directory {path} created.")
        except Exception as e:
            print(f"[ERROR] Error creating directory {path}: {e}")

def _sanitize_export_component(value, default='data'):
    """Return a path-safe filename component."""
    if value is None:
        return ''

    component = str(value).strip()
    component = component.replace(os.sep, '_')
    if os.altsep:
        component = component.replace(os.altsep, '_')
    component = component.replace('..', '_')
    component = re.sub(r'[^A-Za-z0-9._-]+', '_', component)
    component = component.strip('._')
    return component or default

def generate_export_filepath(symbol, data_category, timeframe, file_extension):
    """Generate a file path for exporting data, including the current timestamp.

    This function constructs a file path based on the provided symbol, data category,
    and file extension. The generated path will include a timestamp to ensure uniqueness.

    Parameters
    ----------
    symbol : str
        The symbol to include in the file name, formatted in lowercase.
    data_category : str
        The category of data being exported, which will be prefixed in the file name.
    file_extension : str
        The file extension for the export file (e.g., '.json', '.csv').
    timeframe: str
        Timeframe of report like (e.g., '1M', '1W').

    Returns
    -------
    str
        The generated file path, structured as:
        "<current_directory>/export/<data_category>_<symbol>_<timestamp><file_extension>".
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    unique_suffix = f"{time_ns()}-{uuid.uuid4().hex}"
    safe_category = _sanitize_export_component(data_category)
    safe_symbol = _sanitize_export_component(symbol.lower()) if symbol else ''
    safe_timeframe = _sanitize_export_component(timeframe) if timeframe else ''
    symbol_part = f'{safe_symbol}_' if safe_symbol else ''
    timeframe_part = f'{safe_timeframe}_' if safe_timeframe else ''

    root_path = os.getcwd()
    export_dir = os.path.abspath(os.path.join(root_path, "export"))
    filename = f"{safe_category}_{symbol_part}{timeframe_part}{timestamp}_{unique_suffix}{file_extension}"
    path = os.path.abspath(os.path.join(export_dir, filename))

    if os.path.commonpath([export_dir, path]) != export_dir:
        raise ValueError("Generated export path escapes the export directory")

    return path

def time_ns():
    return time.time_ns()

def _atomic_replace(write_callback, output_path):
    directory = os.path.dirname(output_path)
    ensure_export_directory(directory)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile('w', dir=directory, delete=False) as tmp:
            temp_path = tmp.name
            write_callback(tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise

def save_json_file(data, **kwargs):
    """
    Save the provided data to a JSON file with a generated file path.

    This function creates a JSON file using the specified symbol and data category
    to generate a unique file name. The file is saved in the 'export' directory.

    Parameters
    ----------
    data : dict
        The data to be saved in the JSON file. Must be serializable to JSON format.
    **kwargs : dict
        Additional parameters for file naming:
        - symbol (str): The symbol to include in the file name, formatted to lowercase.
        - data_category (str): The category of the data, used to distinguish between different datasets.
        - timeframe (str, optional): The timeframe for the data, which can be included in the file name. Defaults to an empty string.

    Raises
    ------
    FileNotFoundError
        If the directory for the output path does not exist.
    PermissionError
        If permission is denied when trying to write to the file.
    TypeError
        If the data provided is not serializable to JSON.
    Exception
        For any unexpected errors that may occur during file writing.
    """
    symbol = kwargs.get('symbol')
    data_category = kwargs.get('data_category')
    timeframe = kwargs.get('timeframe', '')
    
    output_path = generate_export_filepath(symbol, data_category, timeframe, '.json')
    try:
        def write_json(file_obj):
            json.dump(data, file_obj, ensure_ascii=False, indent=2)

        _atomic_replace(write_json, output_path)
        print(f"[INFO] JSON file saved at: {output_path}")
    except FileNotFoundError:
        print(f"[ERROR] Error: The directory for {output_path} does not exist.")
    except PermissionError:
        print(f"[ERROR] Error: Permission denied when trying to write to {output_path}.")
    except TypeError as e:
        print(f"[ERROR] Error: The data provided is not serializable. {e}")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")

def save_csv_file(data, **kwargs):
    """
    Save the provided data to a CSV file with a generated file path.

    This function creates a CSV file using the specified symbol and data category
    to generate a unique file name. The file is saved in the 'export' directory.

    Parameters
    ----------
    data : dict
        The data to be saved in the CSV file. Must be in a suitable format for a DataFrame.
    **kwargs : dict
        Additional parameters for file naming:
        - symbol (str): The symbol to include in the file name, formatted to lowercase.
        - data_category (str): The category of the data, used to distinguish between different datasets.
        - timeframe (str, optional): The timeframe for the data, which can be included in the file name. Defaults to an empty string.

    Raises
    ------
    ValueError
        If the data provided is not in a suitable format for a DataFrame.
    FileNotFoundError
        If the directory for the output path does not exist.
    PermissionError
        If permission is denied when trying to write to the file.
    Exception
        For any unexpected errors that may occur during file writing.
    """
    symbol = kwargs.get('symbol')
    data_category = kwargs.get('data_category')
    timeframe = kwargs.get('timeframe', '')

    output_path = generate_export_filepath(symbol, data_category, timeframe, '.csv')
    try:
        df = pd.DataFrame.from_dict(data)

        def write_csv(file_obj):
            df.to_csv(file_obj, index=False)

        _atomic_replace(write_csv, output_path)
        print(f"[INFO] CSV file saved at: {output_path}")
    except ValueError as e:
        print(f"[ERROR] Error: The data provided is not in a suitable format for a DataFrame. {e}")
    except FileNotFoundError:
        print(f"[ERROR] Error: The directory for {output_path} does not exist.")
    except PermissionError:
        print(f"[ERROR] Error: Permission denied when trying to write to {output_path}.")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")

class Exporter:
    """Exports scraper results using the existing JSON/CSV helper functions."""

    def __init__(self, export_type='json'):
        self.export_type = export_type

    def export(self, data, symbol=None, data_category=None, timeframe=''):
        if self.export_type == 'json':
            save_json_file(data=data, symbol=symbol, data_category=data_category, timeframe=timeframe)
        elif self.export_type == 'csv':
            save_csv_file(data=data, symbol=symbol, data_category=data_category, timeframe=timeframe)

def generate_user_agent():
    """
    Generates a random user agent string from a predefined list of Google bot user agents.

    Returns
    -------
    str
        A random Google bot user agent string.
    """
    user_agents = [
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Googlebot-Image/1.0; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Googlebot-News; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Googlebot-Video/1.0; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Googlebot-AdsBot/1.0; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Google-Site-Verification/1.0; +http://www.google.com/bot.html)"
    ]
    
    return random.choice(user_agents)

def validate_string_array(data: List[str], valid_values: List[str]) -> bool:
    """
    Validates a list of strings against a list of valid values.

    This function checks if each item in the provided list of strings is present in the list of valid values.

    Parameters
    ----------
    data : list[str]
        The list of strings to validate.

    valid_values : list[str]
        The list of valid values to check against.

    Returns
    -------
    bool
        True if all items in the data list are valid, False otherwise.
    """
    
    if not data:
        return False

    for item in data:
        if item not in valid_values:
            return False
    
    return True
