import pandas as pd
import os
import pprint

# --- Part 1: Helper Function ---
def clean_hts(code):
    """Takes any HTS code and returns a clean string of only the digits."""
    return ''.join(filter(str.isdigit, str(code)))

# In tariff_engine.py, replace your existing load_all_data function with this one.

def load_all_data():
    """
    Loads and cleans all data files, explicitly setting HTS_Code columns to a
    string data type to prevent scientific notation issues.
    """
    data_path = 'data'
    data_frames = {}
    print("Starting data loading process...")

    # --- Load General Rates & Descriptions Data from CSV ---
    try:
        general_path = os.path.join(data_path, 'Final_HTS.csv')
        # THIS IS THE FIX: dtype={'HTS_Code': str} forces the column to be read as text.
        general_df = pd.read_csv(general_path, dtype={'HTS_Code': str})
        general_df['HTS_Code_Clean'] = general_df['HTS_Code'].apply(clean_hts)
        data_frames['general'] = general_df
        print(f"Successfully loaded and cleaned: {os.path.basename(general_path)}")
    except Exception as e:
        print(f"ERROR loading Final_HTS.csv: {e}.")

    # --- Load Section 301 Data ---
    try:
        s301_path = os.path.join(data_path, 'Section_301.csv')
        # Applying the same fix here for robustness
        s301_df = pd.read_csv(s301_path, dtype={'HTS_Code': str})
        s301_df['HTS_Code_Clean'] = s301_df['HTS_Code'].apply(clean_hts)
        data_frames['s301'] = s301_df
        print(f"Successfully loaded and cleaned: {os.path.basename(s301_path)}")
    except Exception as e:
        print(f"ERROR loading Section_301.csv: {e}.")

    # --- Load Section 232 Data Files ---
    s232_files = {
        's232_2024': '2024_Section_232_data.csv',
        's232_pre_may_25': 'Pre_May_25_Section_232_data.csv',
        's232_post_may_25': 'Post_May_25_Section_232_data.csv'
    }
    for key, filename in s232_files.items():
        try:
            file_path = os.path.join(data_path, filename)
            # Applying the same fix here for robustness
            df = pd.read_csv(file_path, dtype={'HTS_Code': str})
            df['HTS_Code_Clean'] = df['HTS_Code'].apply(clean_hts)
            data_frames[key] = df
            print(f"Successfully loaded and cleaned: {filename}")
        except Exception as e:
            print(f"ERROR loading {filename}: {e}.")
            
    print("--- Data loading complete. ---")
    return data_frames

# --- Part 3: Individual Tariff Calculation Functions ---
def get_section_301_rate(hts_code, country, s301_df):
    """Calculates the Section 301 tariff. Returns rate as a decimal (e.g., 0.25 for 25%)."""
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

# In tariff_engine.py, replace the get_section_232_rate function.

def get_section_232_rate(hts_code, scenario_df):
    """
    Performs a robust hierarchical lookup (10, 8, 6, then 4-digit) for Section 232.
    """
    clean_code = clean_hts(hts_code)
    
    # --- THIS IS THE FIX ---
    # The search now starts from 10 digits.
    for length in [10, 8, 6, 4]:
        target_code = clean_code[:length]
        match = scenario_df.loc[scenario_df['HTS_Code_Clean'] == target_code]
        if not match.empty:
            try:
                duty_rate = float(match.iloc[0]['Section 232 Duty'])
                # e.g. if file has 25, we convert to 0.25
                return duty_rate / 100.0
            except (ValueError, TypeError):
                continue
            
    return 0.0

def get_ieepa_rate(country, scenario_name):
    """Calculates the IEEPA tariff based on fixed rules."""
    if country.lower() == 'china' and scenario_name in ['s232_pre_may_25', 's232_post_may_25']:
        return 0.20
    return 0.0

def get_reciprocal_rate(country, scenario_name):
    """Calculates the Reciprocal tariff based on fixed rules."""
    country_lower = country.lower()
    if scenario_name == 's232_2024':
        return 0.0
    elif scenario_name == 's232_pre_may_25' and country_lower == 'china':
        return 1.25
    elif scenario_name == 's232_post_may_25' and country_lower == 'china':
        return 0.10
    return 0.0

# --- Part 4: Main Calculation Engine and Test Block ---
# In tariff_engine.py, replace the old calculate_all_tariffs function with this one.

# In tariff_engine.py, replace the entire calculate_all_tariffs function with this version.

def calculate_all_tariffs(hts_code, country, all_data, general_rate):
    """
    The main engine. It now correctly uses the general_rate passed into it.
    """
    final_results = {}
    scenarios = {
        '2024 Tariff': ('s232_2024', '2024_Section_232_data.csv'),
        'Pre-May 2025': ('s232_pre_may_25', 'Pre_May_25_Section_232_data.csv'),
        'Post-May 2025': ('s232_post_may_25', 'Post_May_25_Section_232_data.csv')
    }

    for scenario_display_name, (scenario_key, scenario_filename) in scenarios.items():
        # --- THIS IS THE FIX ---
        # The old placeholder 'general_rate = 0.0' has been removed from here.
        # The function will now use the 'general_rate' value that is passed into it.
        
        # Call individual lookup functions
        s301_rate = get_section_301_rate(hts_code, country, all_data['s301'])
        s232_rate = get_section_232_rate(hts_code, all_data[scenario_key])
        ieepa_rate = get_ieepa_rate(country, scenario_key)
        reciprocal_rate = get_reciprocal_rate(country, scenario_key)
        
        scenario_result = {
            'components': {
                'General Rate': general_rate, 'Section 301': s301_rate,
                'IEEPA': ieepa_rate, 'Section 232': s232_rate, 'Reciprocal': reciprocal_rate
            }
        }
        
        if s232_rate > 0:
            scenario_result['is_composite'] = True
            scenario_result['Metal Component Tariff %'] = general_rate + s301_rate + ieepa_rate + s232_rate
            scenario_result['Other Component Tariff %'] = general_rate + s301_rate + ieepa_rate + reciprocal_rate
        else:
            scenario_result['is_composite'] = False
            scenario_result['Total Tariff %'] = general_rate + s301_rate + ieepa_rate + s232_rate + reciprocal_rate
        
        final_results[scenario_display_name] = scenario_result
    return final_results

# In tariff_engine.py, replace the entire test block at the end of the file.

if __name__ == "__main__":
    # This special block runs only when you execute "python tariff_engine.py" directly
    all_dataframes = load_all_data()
    
    # Only proceed with the test if the dataframes were loaded successfully
    if all_dataframes:
        TEST_HTS_CODE = "7302.90.00"
        TEST_COUNTRY = "China"
        
        # This is the placeholder for the General Rate for testing purposes.
        TEST_GENERAL_RATE = 0.0
        
        print(f"\n=========================================")
        print(f"RUNNING TEST CALCULATION FOR:")
        print(f"HTS Code: {TEST_HTS_CODE}, Country: {TEST_COUNTRY}")
        print(f"=========================================")
        
        # --- THIS IS THE CORRECTED LINE ---
        # We now pass the TEST_GENERAL_RATE as the fourth argument.
        calculated_tariffs = calculate_all_tariffs(
            TEST_HTS_CODE, 
            TEST_COUNTRY, 
            all_dataframes, 
            TEST_GENERAL_RATE
        )
        
        print("\n================ FINAL RESULT =================")
        pprint.pprint(calculated_tariffs)
    else:
        print("\nTesting aborted due to data loading errors.")