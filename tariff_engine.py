import pandas as pd
import os
import pprint

# ==============================================================================
# Part 1: Helper Function
# ==============================================================================
def clean_hts(code):
    """
    Takes any HTS code and returns a clean string of only the digits.
    """
    return ''.join(filter(str.isdigit, str(code)))


# ==============================================================================
# Part 2: Main Data Loading Function
# ==============================================================================
def load_all_data():
    """
    Loads and cleans all required data files, explicitly setting HTS_Code 
    columns to a string data type to prevent errors.
    """
    data_path = 'data'
    data_frames = {}
    print("Starting data loading process...")

    files_to_load = {
        'general': ('Final_HTS.csv', 'HTS_Code'),
        's301': ('Section_301.csv', 'HTS_Code'),
        's232_2024': ('2024_Section_232_data.csv', 'HTS_Code'),
        's232_pre_may_25': ('Pre_May_25_Section_232_data.csv', 'HTS_Code'),
        's232_post_may_25': ('Post_May_25_Section_232_data.csv', 'HTS_Code'),
        'reciprocal_pre_may_25': ('Pre_May_25_Reciprocal_Tariffs.csv', None),
        'reciprocal_post_may_25': ('Post_May_25_Reciprocal_Tariffs.csv', None)
    }

    for key, (filename, hts_col_name) in files_to_load.items():
        try:
            file_path = os.path.join(data_path, filename)
            dtype = {hts_col_name: str} if hts_col_name else None
            df = pd.read_csv(file_path, dtype=dtype)
            
            if hts_col_name:
                df['HTS_Code_Clean'] = df[hts_col_name].apply(clean_hts)

            data_frames[key] = df
            print(f"Successfully loaded and cleaned: {filename}")
        except Exception as e:
            print(f"CRITICAL ERROR loading {filename}: {e}. The app may not function correctly.")
            
    print("--- Data loading complete. ---")
    return data_frames


# ==============================================================================
# Part 3: Individual Tariff Calculation Functions
# ==============================================================================
def get_section_301_rate(hts_code, country, s301_df):
    """Calculates the Section 301 tariff. Returns rate as a decimal."""
    if country.lower() != 'china':
        return 0.0
    clean_code_8_digit = clean_hts(hts_code)[:8]
    match = s301_df.loc[s301_df['HTS_Code_Clean'].str.startswith(clean_code_8_digit)]
    if not match.empty:
        try:
            duty_rate = float(match.iloc[0]['Section 301 Tariff %'])
            return duty_rate / 100.0
        except (ValueError, TypeError):
            return 0.0
    return 0.0

def get_section_232_rate(hts_code, scenario_df):
    """Performs robust hierarchical lookup (10, 8, 6, 4-digit). Returns rate as a decimal."""
    clean_code = clean_hts(hts_code)
    for length in [10, 8, 6, 4]:
        target_code = clean_code[:length]
        match = scenario_df.loc[scenario_df['HTS_Code_Clean'] == target_code]
        if not match.empty:
            try:
                duty_rate = float(match.iloc[0]['Section 232 Duty'])
                return duty_rate / 100.0
            except (ValueError, TypeError):
                continue
    return 0.0

def get_ieepa_rate(country, scenario_key):
    """Calculates the IEEPA tariff based on fixed rules."""
    if country.lower() == 'china' and scenario_key in ['s232_pre_may_25', 's232_post_may_25']:
        return 0.20
    return 0.0

def get_reciprocal_rate(country, scenario_key, all_data):
    """
    Calculates the Reciprocal tariff based on a lookup in the data files.
    """
    if scenario_key == 's232_2024':
        return 0.0

    df_key_map = {
        's232_pre_may_25': 'reciprocal_pre_may_25',
        's232_post_may_25': 'reciprocal_post_may_25'
    }
    df_key = df_key_map.get(scenario_key)
    if not df_key or df_key not in all_data:
        return 0.0
        
    reciprocal_df = all_data[df_key]
    
    country_col = 'Country'
    tariff_col = 'Reciprocal_Tariffs'
    
    if country_col not in reciprocal_df.columns or tariff_col not in reciprocal_df.columns:
        print(f"ERROR: Missing '{country_col}' or '{tariff_col}' column in the file for {df_key}.")
        return 0.0
    
    match = reciprocal_df.loc[reciprocal_df[country_col].str.lower() == country.lower()]
    
    if not match.empty:
        try:
            duty_rate = float(match.iloc[0][tariff_col])
            return duty_rate / 100.0
        except (ValueError, TypeError):
            return 0.0
            
    return 0.0

# ==============================================================================
# Part 4: Main Calculation Engine
# ==============================================================================
def calculate_all_tariffs(hts_code, country, all_data, general_rate):
    """The main engine. Orchestrates the calculation process for all scenarios."""
    final_results = {}
    scenarios = {
        '2024 Tariff': 's232_2024',
        'Pre-May 2025': 's232_pre_may_25',
        'Post-May 2025': 's232_post_may_25'
    }

    required_dfs = ['s301', 's232_2024', 's232_pre_may_25', 's232_post_may_25', 'reciprocal_pre_may_25', 'reciprocal_post_may_25']
    if not all(key in all_data for key in required_dfs):
        return {"error": "One or more data files failed to load. Please check the console."}

    for scenario_display_name, scenario_key in scenarios.items():
        s301_rate = get_section_301_rate(hts_code, country, all_data['s301'])
        s232_rate = get_section_232_rate(hts_code, all_data[scenario_key])
        ieepa_rate = get_ieepa_rate(country, scenario_key)
        reciprocal_rate = get_reciprocal_rate(country, scenario_key, all_data)
        
        # Calculate the single Total Tariff % for all cases by summing components.
        total_tariff_percent = general_rate + s301_rate + ieepa_rate + s232_rate + reciprocal_rate
        
        scenario_result = {
            'components': {
                'General Rate': general_rate,
                'Section 301': s301_rate,
                'IEEPA': ieepa_rate,
                'Section 232': s232_rate,
                'Reciprocal': reciprocal_rate
            },
            'Total Tariff %': total_tariff_percent
        }
        
        # We still note if it's composite for the single lookup UI's interactive part.
        if s232_rate > 0:
            scenario_result['is_composite'] = True
            scenario_result['Metal Component Tariff %'] = general_rate + s301_rate + ieepa_rate + s232_rate
            scenario_result['Other Component Tariff %'] = general_rate + s301_rate + ieepa_rate + reciprocal_rate
        else:
            scenario_result['is_composite'] = False
        
        final_results[scenario_display_name] = scenario_result
    return final_results
