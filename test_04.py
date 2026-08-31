'''
Copyright 2026-2027 Accolade Electronics Pvt. Ltd

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
version 2 as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

file        test_04.py
brief       This is the source file for the Atcu testing integration

date        25-3-2026
author      Accolade Electronics <www.accoladeelectronics.com>
Developed by   Anjanrav Dhole
'''
import tkinter as tk
from tkinter import simpledialog
from tkinter import messagebox
import pandas as pd
import serial
import re
import time
from datetime import datetime
import tkinter
import os
import sys
import openpyxl

stop_button_status = None
global flag

import json


def resource_path(relative_path):
    """Return a path valid for both source runs and PyInstaller bundles."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


config_path = resource_path('config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

HW_VERSION_WIFI = config['hardware_versions']['wifi']
HW_VERSION_NON_WIFI = config['hardware_versions']['non_wifi']
ECUID_WIFI = config['ecuid']['wifi']
ECUID_NON_WIFI = config['ecuid']['non_wifi']

# Make these global so they can be accessed by other functions
global subfolder_path, current_date, current_day, current_month_year, log_file_path, exe_file_path

current_date = datetime.now().strftime("%Y-%m-%d")
current_day = datetime.now().strftime("%A")
current_month_year = datetime.now().strftime("%B_%Y")
month_folder_path = current_month_year
subfolder_path = os.path.join(month_folder_path, f"{current_date}_{current_day}")

if not os.path.exists(subfolder_path):
    os.makedirs(subfolder_path)
log_file_path = os.path.join(subfolder_path, f"serial_log_{current_date}.txt")

if not os.path.exists(log_file_path):
    with open(log_file_path, 'x', encoding='utf-8', errors='replace') as log_file:
        log_file.write("Serial Port Log\n")
exe_file_path = os.path.join(subfolder_path, f"Exe_{current_date}.exe")


def save_to_log(log_file_path, data):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file_path, 'a', encoding='utf-8', errors='replace') as log_file:
        log_file.write(f"{timestamp}: {data}\n")


################################## INITIAL CMD ######################################
def write_initial_commands(ser, stop_event):
    if stop_event.is_set():
        ser.close()
        return "STOPPED", 0, "False", "False", None, None  # Added imei and iccid as None
    try:
        time.sleep(0.5)
        ser.write(b'$CONFIG_UIN,ACON4NAXXXXAAAABBBB')
        time.sleep(2)
        ser.write(b'$REBOOT')
        print("Entering into Application mode.")
        time.sleep(2)
    except Exception as e:
        print(f"Error in write_initial_commands: {e}")
        raise


def write_final_commands(ser, stop_event):
    if stop_event.is_set():
        ser.close()
        return "STOPPED", 0, "False", "False", None, None  # Added imei and iccid as None
    try:
        ser.write(b'*SET#LOGFLTR#65533#')
        time.sleep(0.5)
        ser.write(b'*CLR#UIN#')
        print("Entering into Line Automation mode..")  # Fixed typo
    except Exception as e:
        print(f"Error in write_final_commands: {e}")
        raise


def extract_gsm_data_from_serial_regex(ser, stop_event):
    """
    Uses regex to parse GSM data and extract IMEI and ICCID.
    More robust for varying line formats.
    """
    imei = None
    iccid = None

    print("Starting GSM monitoring (timeout: 2 minutes)...")
    timeout = time.time() + 60 * 4

    while time.time() < timeout:
        if stop_event.is_set():
            ser.close()
            return "STOPPED", None, None

        try:
            line = ser.readline().decode('utf-8', errors='replace').strip()
            if not line:
                continue
            save_to_log(log_file_path, line)
            pattern = r'\$GSM,([^,]+),([^,]+)'
            match = re.search(pattern, line)
            if match:
                imei = match.group(1)
                iccid = match.group(2)
                print(f"  - IMEI: {imei}")
                print(f"  - ICCID: {iccid}")
                return imei, iccid
        except Exception as e:
            print(f"Error reading GSM line: {e}")
            continue

    print(f"GSM data extraction failed after timeout.")
    return None, None


##############date and time###########
def extract_data_from_program1(ser):
    try:
        c = datetime.now()
        current_time = c.strftime('%H:%M:%S')
        today = c.date()  # Use the date portion only
        df1 = pd.DataFrame({'Date': [today.strftime('%Y-%m-%d')], 'Current Time': [current_time]})
        return df1
    except Exception as e:
        print(f"Error in extract_data_from_program1: {e}")
        return pd.DataFrame({'Date': ['error'], 'Current Time': ['error']})

def extract_emmc_manufacturer_from_serial(ser, stop_event):
    manufacturer_name = None
    manufacturer_id = None
    product_name = None
    data_refresh_hex = None
    detected_emmc = None

    max_retries = 2
    retry_count = 0

    EXPECTED_EMMCS = {
        "00000015": {
            "manufacturer": "Samsung",
            "product": "8GUF4",
            "data_refresh": "00000002"
        },
        "00000090": {
            "manufacturer": "SK Hynix",
            "product": "H8G4a"
        }
    }

    while retry_count <= max_retries:

        manufacturer_name = None
        manufacturer_id = None
        product_name = None
        data_refresh_hex = None
        detected_emmc = None

        if retry_count > 0:
            print(f"Retry attempt {retry_count}/{max_retries} for eMMC manufacturer extraction...")
            time.sleep(2)

        ser.write(b'*SET#CRST#1#')
        time.sleep(0.5)

        print(f"Starting eMMC manufacturer monitoring (timeout: 1 minute)... Attempt {retry_count + 1}")

        timeout = time.time() + 60

        while time.time() < timeout:

            if stop_event.is_set():
                ser.close()
                return "STOPPED", None, None, None, None, None

            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()

                if not line:
                    continue

                save_to_log(log_file_path, line)

                # Manufacturer Name
                name_pattern = r'Manufacturer Name\s+\[([^\]]+)\]'
                name_match = re.search(name_pattern, line)

                if name_match:
                    manufacturer_name = name_match.group(1).strip()
                    print(f"  - Manufacturer Name: {manufacturer_name}")

                # Manufacturer ID
                id_pattern = r'Manufacturer ID\s+\[([0-9A-Fa-f]+)\]'
                id_match = re.search(id_pattern, line)

                if id_match:
                    manufacturer_id = id_match.group(1).strip().upper()
                    print(f"  - Manufacturer ID: {manufacturer_id}")

                # Product Name
                product_name_pattern = r'Product Name\s+\[([A-Za-z0-9]+)\]'
                product_match = re.search(product_name_pattern, line)

                if product_match:
                    product_name = product_match.group(1).strip()
                    print(f"  - Product Name: {product_name}")

                # Data Refresh Setting
                data_refresh_pattern = r'Data Refresh Setting\s+\[([0-9A-Fa-f]+)\]'
                data_refresh_match = re.search(data_refresh_pattern, line)

                if data_refresh_match:
                    data_refresh_hex = data_refresh_match.group(1).strip().upper()
                    print(f"  - Data Refresh Setting: {data_refresh_hex}")

                # Check Manufacturer ID
                if manufacturer_id in EXPECTED_EMMCS:

                    expected = EXPECTED_EMMCS[manufacturer_id]

                    # Common validation
                    basic_info_valid = (
                        manufacturer_name
                        and product_name
                        and manufacturer_name.lower() == expected["manufacturer"].lower()
                        and product_name.lower() == expected["product"].lower()
                    )

                    if basic_info_valid:

                        # Samsung requires Data Refresh Setting validation
                        if manufacturer_id == "00000015":

                            if data_refresh_hex == expected["data_refresh"]:
                                detected_emmc = "Samsung"

                        # SK Hynix does NOT require Data Refresh Setting
                        elif manufacturer_id == "00000090":
                            detected_emmc = "SK Hynix"

                        # If valid eMMC detected
                        if detected_emmc:

                            print(f"Detected eMMC: {detected_emmc}")

                            df11 = pd.DataFrame({
                                'Manufacturer Name': [manufacturer_name],
                                'Manufacturer ID': [manufacturer_id],
                                'Product Name': [product_name],
                                'Data Refresh Setting': [data_refresh_hex],
                                'Detected eMMC': [detected_emmc]
                            })

                            return (
                                df11,
                                manufacturer_name,
                                manufacturer_id,
                                product_name,
                                data_refresh_hex,
                                detected_emmc
                            )

            except Exception as e:
                print(f"Error reading eMMC line: {e}")
                continue

        if manufacturer_name or manufacturer_id or product_name or data_refresh_hex:
            print(
                f"Partial data found - "
                f"Manufacturer Name: {manufacturer_name}, "
                f"ID: {manufacturer_id}, "
                f"Product Name: {product_name}, "
                f"Data Refresh Setting: {data_refresh_hex}"
            )

        retry_count += 1

    print(f"eMMC manufacturer extraction failed after {max_retries + 1} attempts.")

    return None, None, None, None, None, None

def extract_data_from_program2(ser):
    time.sleep(0.5)
    ser.write(b'*SET#CRST#1#')
    #print("hw/sw reset successfully")

    keyword_hardware = "######## HARDWARE"
    keyword_software = "######## SOFTWARE"

    data_associated_with_keyword_hardware = ""
    data_associated_with_keyword_software = ""

    while True:
        line = ser.readline().decode('utf-8', errors='replace').strip()
        save_to_log(log_file_path, line)

        if keyword_hardware in line:
            data_associated_with_keyword_hardware = re.search(rf'{re.escape(keyword_hardware)}\s*:\s*(.*)', line)
            if data_associated_with_keyword_hardware:
                data_associated_with_keyword_hardware = data_associated_with_keyword_hardware.group(1)

        if keyword_software in line:
            data_associated_with_keyword_software = re.search(rf'{re.escape(keyword_software)}\s*:\s*(.*)', line)
            if data_associated_with_keyword_software:
                data_associated_with_keyword_software = data_associated_with_keyword_software.group(1)

        # Break if both hardware and software data are obtained
        if data_associated_with_keyword_hardware and data_associated_with_keyword_software:
            break

    size_of_data = 16
    limited_data_hardware = data_associated_with_keyword_hardware[:size_of_data]
    limited_data_software = data_associated_with_keyword_software[:size_of_data]

    df2 = pd.DataFrame({'Hardware Details': [limited_data_hardware], 'Software Details': [limited_data_software]})
    return df2


############### KEYWORDS ################
def extract_data_from_program3(ser):
    time.sleep(5)
    # Add stop_event check at the beginning
    df2 = extract_data_from_program2(ser)
    print("Checking for default parameters..")

    default_parameters = {
        'aepl srvr': 'atcu-data.accoladeelectronics.com : 6100',
        'ais pri srvr': '255.255.255.255   : 65535',
        'ais emg srvr': '255.255.255.255   : 65535',
        'tml http srvr': 'cva4g.cvppp.digital.tatamotors : 8883',
        'tml mqtt srvr': 'cva4g.cvppp.digital.tatamotors : 8883',
        'can loging intrvl': 30,
        'tele loging intrvl': 5,
        'gen can intrvl': 60,
        'tdps': 0,
        'num fuel tanks': 1,
        'aft autdetect done': 0,
        'aft enable': 0,
        'use ssl cert': 1,
        'tcu ecu id': ['0018FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF', '0017FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF'],
        'emmc certificate': '#0,0,0',
        'tml telmtry intrvl': 60  # Added this to default parameters
    }
    keywords_and_columns = {
        'ais pri srvr': 'ais.ip:port(CHTP)',
        'ais emg srvr': 'aepl.ip1.port(CIP1)',
        'aepl srvr': 'aepl.ip1.port(CIP2)',
        'tml http srvr': 'tml.ip:port',
        'tml mqtt srvr': 'tml.ip:port(CIP3)',
        'tml telmtry intrvl': 'tml.pvtSec (Sending) (TNPIN)60',
        'tele loging intrvl': 'tml.pvtSec (loging)(TLPIN)5',
        'gen can intrvl': 'tml.canSec(sending)(CPIN)',
        'can loging intrvl': 'tml.canSec(loging) (CLPIN)30',
        'tdps': 'TDPS (value=0)',
        'num fuel tanks': 'No of fuel tank (NOFT)(value=1)',
        'aft autdetect done': 'AFT autodetection flag(AFTAD)(value=0)',
        'aft enable': 'AFT Enable(AFT) value=0',
        'use ssl cert': 'tml.sslConfig',
        'software version': 'Software Version',
        'hardware version': 'Hardware Version',
        'tcu ecu id': 'ECUID',
        'iccid': 'ICCID',
        'imei': 'IMEI',
    }

    data_associated_with_keywords = {keyword: "" for keyword in keywords_and_columns.keys()}
    column_limits = {
        'ais pri srvr': 37,
        'ais emg srvr': 37,
        'aepl srvr': 52,
        'tml http srvr': 49,
        'tml mqtt srvr': 49,
        'tml telmtry intrvl': 14,
        'tele loging intrvl': 13,
        'gen can intrvl': 14,
        'can loging intrvl': 14,
        'tdps': 13,
        'num fuel tanks': 13,
        'aft autdetect done': 13,
        'aft enable': 13,
        'use ssl cert': 13,
        'software version': 27,
        'hardware version': 27,
        'tcu ecu id': 52,
        'iccid': 32,
        'imei': 27,
    }

    # Retry configuration
    max_retries = 1  # Maximum number of retries
    retry_delay = 2  # Delay in seconds between retries
    retry_count = 0

    while retry_count <= max_retries:
        if retry_count > 0:
            time.sleep(retry_delay)

        data_associated_with_keywords = {keyword: "" for keyword in keywords_and_columns.keys()}
        timeout_start = time.time()
        timeout_duration = 20  # 30 seconds timeout for each attempt

        while True:
            # Check for timeout
            if time.time() - timeout_start > timeout_duration:
                retry_count + 1
            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                save_to_log(log_file_path, line)
                for keyword in keywords_and_columns.keys():
                    match = re.search(rf'{keyword}\s+\|\s+(.*)', line)
                    if match:
                        data = match.group(1)[:column_limits[keyword]]
                        data_associated_with_keywords[keyword] = data.strip()

            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")
                continue

            # Check if all data is collected
            if all(data_associated_with_keywords.values()):
                processed_data = {keyword: re.sub(r'^\s*\w+\s*', '', data).strip() for keyword, data in
                                  data_associated_with_keywords.items()}

                hardware_version = df2['Hardware Details'].iloc[0].strip()

                ecuid_wifi = "0018FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
                ecuid_non_wifi = "0017FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"

                default_parameter_status = "unavailable"

                # Check the value of tml telmtry intrvl
                tml_telmtry_intrvl = processed_data.get('tml telmtry intrvl', '').strip()

                try:
                    if tml_telmtry_intrvl == '60':
                        if hardware_version == HW_VERSION_WIFI and processed_data.get('tcu ecu id', '') == ECUID_WIFI:
                            if all(str(processed_data[key]) == str(default_parameters[key]) for key in processed_data if
                                   key not in ['imei', 'iccid', 'software version', 'hardware version',
                                               'Hardware Details', 'Software Details', 'tcu ecu id',
                                               'tml telmtry intrvl']):
                                default_parameter_status = "available"
                        elif hardware_version == HW_VERSION_NON_WIFI and processed_data.get('tcu ecu id',
                                                                                            '') == ECUID_NON_WIFI:
                            if all(str(processed_data[key]) == str(default_parameters[key]) for key in processed_data if
                                   key not in ['imei', 'iccid', 'software version', 'hardware version',
                                               'Hardware Details', 'Software Details', 'tcu ecu id',
                                               'tml telmtry intrvl']):
                                default_parameter_status = "available"
                except Exception as e:
                    print(f"Error while checking parameters: {e}")

                print(f"Default Parameter are: {default_parameter_status}")

                # If status is available, create and return DataFrame
                if default_parameter_status == "available":
                    df3 = pd.DataFrame({keywords_and_columns[keyword]: [processed_data.get(keyword, '')] for keyword in
                                        keywords_and_columns})
                    df3['default parameter'] = default_parameter_status

                    # Ensure IMEI number is treated as text
                    if 'IMEI' in keywords_and_columns.values():
                        df3['IMEI'] = df3['IMEI'].astype(str)
                    df3 = pd.concat([df3, df2], axis=1)
                    return df3
                else:
                    # If status is unavailable and we have retries left, break and retry
                    if retry_count < max_retries:
                        time.sleep(15)
                        print(f"Default parameters not verified. again rechecking...")
                        df2 = extract_data_from_program2(ser)
                        break  # Break current attempt to retry
                    else:
                        df3 = pd.DataFrame(
                            {keywords_and_columns[keyword]: [processed_data.get(keyword, '')] for keyword in
                             keywords_and_columns})
                        df3['default parameter'] = default_parameter_status

                        if 'IMEI' in keywords_and_columns.values():
                            df3['IMEI'] = df3['IMEI'].astype(str)
                        df3 = pd.concat([df3, df2], axis=1)
                        return df3

        # Increment retry count for next attempt
        retry_count += 1
        if retry_count > max_retries:
            break
    df3 = pd.DataFrame({col: [''] for col in keywords_and_columns.values()})
    df3['default parameter'] = "unavailable"
    df3 = pd.concat([df3, df2], axis=1)
    return df3

def extract_data_from_program4(ser, stop_event):
    max_retries = 2
    attempt = 0
    data_associated_with_keyword4 = ""
    while attempt <= max_retries:
        ser.write(b'*GET#CERT#')
        print(f"*GET#CERT# applied (Attempt {attempt + 1})")
        start_time = time.time()
        while time.time() - start_time < 5:  # Wait up to 5 seconds per attempt
            if stop_event.is_set():
                ser.close()
                return "STOPPED", 0, "False", "False", None, None  # Added imei and iccid as None
            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if line:
                    save_to_log(log_file_path, line)

                match = re.search(r'INFO:\s+\[FOT\]\s+console\s+ota\s+response:\s+STATUS#CERT(.+?)#', line)
                if match:
                    data_associated_with_keyword4 = match.group(1)
                    break
            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")
                continue

        if data_associated_with_keyword4:
            break  # Exit retry loop if data found
        else:
            attempt += 1
            time.sleep(2)  # Small delay before retry

    df4 = pd.DataFrame({"QA Certificates on eMMC": [
        data_associated_with_keyword4 if data_associated_with_keyword4 else "Not found"]})
    return df4


##############################Digital status #####################################
def run_extract_analog_status_in_thread(ser, stop_event):
    print("searching DO status")
    new_keyword = 'INFO:  [PLA] ANALOG  INT BATT'  # Adjusted keyword for matching
    numeric_data_associated_with_analog_string = []
    count = 0
    condition_met_DO1 = True  # Start with True, but if any D0 iteration fails, set to False
    condition_met_DO2 = True  # Start with True, but if any D1 iteration fails, set to False

    while True:  # Keep running until the stop_event is set
        if stop_event.is_set():
            ser.close()
            return "STOPPED", 0, "False", "False", None, None  # Added imei and iccid as None
        if count < 2:
            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()  # Read a line from the serial port
                save_to_log(log_file_path, line)  # Log the line

                # Check if the keyword is in the line
                if new_keyword in line:
                    # Extract the two voltage values that come after 'AN'
                    match_analog = re.search(r'AN\s+(\d+\.\d+)V.*?(\d+\.\d+)V', line)
                    if match_analog:
                        DO1 = float(match_analog.group(1))  # First voltage value after 'AN', now called D0
                        DO2 = float(match_analog.group(2))  # Second voltage value after 'AN', now called D1
                        numeric_data_associated_with_analog_string.append((DO1, DO2))

                        print("D01:", DO1, "D02:",DO2)

                        # Check conditions for D0 (voltage 1) and D1 (voltage 2) separately
                        if not (DO1 == 0 or DO1 > 19):
                            condition_met_DO1 = False  # Set condition_met_D0 to False if D0 fails the condition

                        if not (DO2 == 0 or DO2 > 19):
                            condition_met_DO2 = False  # Set condition_met_D1 to False if D1 fails the condition

                        # Increment count only when a valid data point is added
                        count += 1

            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")
            time.sleep(0.5)  # Add a delay between each loop iteration if needed

        # Break the loop once 5 valid data points are collected
        if len(numeric_data_associated_with_analog_string) >= 2:
            break

    # After collecting 5 valid data points, print the final results
    if condition_met_DO1:
        print("End result for DO1: True (Condition met for all sets of D0 voltages)")
    else:
        print("End result for DO1: False (At least one set of D0 voltages failed the condition)")

    if condition_met_DO2:
        print("End result for DO2: True (Condition met for all sets of D1 voltages)")
    else:
        print("End result for DO2: False (At least one set of D1 voltages failed the condition)")

    df9 = pd.DataFrame({'DO1 status': [condition_met_DO1], 'DO2 status': [condition_met_DO2]})
    return df9  # Return the DataFrame


def extract_data_from_program8(ser, stop_event):
    max_retries = 2
    mode = None
    df8 = None

    for attempt in range(max_retries + 1):  # +1 for initial attempt + retries
        if attempt > 0:
            print(f"Retry attempt {attempt} for network scan mode...")
            time.sleep(1)  # Small delay before retry

        # Send the command
        ser.write(b'GSM AT+QCFG="nwscanmode"\r\n')  # Added \r\n for proper command termination
        print(f"Searching for network scan mode... (Attempt {attempt + 1})")

        timeout = time.time() + 30
        full_response = ""  # To store all response lines

        while time.time() < timeout:
            if stop_event.is_set():
                ser.close()
                return "STOPPED", 0, "False", "False", None, None  # Added imei and iccid as None
            try:
                if ser.in_waiting > 0:  # Check if data is available
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        save_to_log(log_file_path, line)
                        full_response += line + "\n"

                        # Check for success response
                        if '+QCFG: "nwscanmode"' in line:
                            # Try to extract mode value
                            # Format expected: +QCFG: "nwscanmode",value
                            # or: +QCFG: "nwscanmode",value,<other_params>
                            parts = line.strip().split(',')
                            if len(parts) > 1:
                                # Get the last part or the part after the quote
                                value_part = parts[-1].strip()
                                # Handle cases where value might be in quotes
                                value_part = value_part.strip('"')
                                if value_part.isdigit():
                                    mode = int(value_part)
                                    df8 = pd.DataFrame({'NWSMode Value': [mode]})
                                    print(f"Successfully extracted mode: {mode} on attempt {attempt + 1}")
                                    return df8, mode  # Success - exit immediately

            except UnicodeDecodeError:
                print("Unicode decode error, skipping line...")
                continue
            except Exception as e:
                print(f"Read error: {e}")
                continue

        if ser.in_waiting > 0:
            ser.reset_input_buffer()

    df8 = pd.DataFrame({'NWSMode Value': [None]})
    return df8, None


def non_blocking_wait(duration, ser, log_file_path):
    start_time = time.time()
    while time.time() - start_time < duration:
        try:
            if ser.in_waiting > 0:
                try:
                    while ser.in_waiting > 0:
                        line = ser.readline().decode('utf-8', errors='replace').strip()
                        if line:
                            save_to_log(log_file_path, line)
                except UnicodeDecodeError as e:
                    print(f"UnicodeDecodeError: {e}")
        except Exception as e:
            print(f"Error in non_blocking_wait: {e}")
        time.sleep(0.1)  # Adjust as necessary


def extract_data_from_program12(ser, stop_event):
    """Continuously reads GPS data, extracts FIX QUA, retries up to 4 times if invalid."""
    retry_count = 0
    max_retries = 2
    fix_quality = None
    print("Starting GPS monitoring (max 2 retries)...")
    timeout = time.time() + 60

    while time.time() < timeout and retry_count < max_retries:
        if stop_event.is_set():
            ser.close()
            return "STOPPED", 0, "False", "False", None, None  # Added imei and iccid as None
        try:
            line = ser.readline().decode('utf-8', errors='replace').strip()
            if not line:
                continue

            save_to_log(log_file_path, line)
            if "INFO:  [PLA] GPS" not in line:
                continue

            pattern = r'(\w+(?: \w+)*) ([\w\.\-]+)'
            matches = re.findall(pattern, line)
            gps_data = {key.strip().replace(" ", "_"): value.strip() for key, value in matches}

            # Get FIX QUA value
            fix_quality = gps_data.get("FIX_QUA")

            if fix_quality is None:
                print("No FIX QUA field found, retrying...")
                retry_count += 1
                time.sleep(2)
                continue

            if fix_quality == "0":
                print(f"FIX QUA = {fix_quality} → GPS Fix Not Valid (Retry {retry_count + 1}/{max_retries})")
                retry_count += 1
                time.sleep(2)
                continue
            elif fix_quality == "1":
                print(f"FIX QUA = {fix_quality} → GPS Fix Valid (Success!)")
                # Return empty DataFrame with no data
                df12 = pd.DataFrame()  # Empty DataFrame
                return df12, fix_quality
            else:
                print(f"FIX QUA = {fix_quality} → Unknown value, retrying...")
                retry_count += 1
                time.sleep(2)
        except Exception as e:
            print(f"Error reading GPS line: {e}")
            continue
    # --- Retries exhausted or no valid GPS fix ---
    print(f"GPS Fix not valid even after {max_retries} retries. Last FIX QUA = {fix_quality}")
    # Return empty DataFrame without fix_quality
    return pd.DataFrame(), fix_quality


################## CSQ ########################
def extract_data_from_program6(ser, stop_event):
    ser.flushInput()
    print("checking CSQ.. ")
    new_keyword = 'INFO:  [PLA] NET     CSQ'
    numeric_data_associated_with_csq = ""
    timeout = time.time() + 30  # 30 second timeout

    while time.time() < timeout:
        if stop_event.is_set():
            ser.close()
            return "STOPPED", 0, "False", "False", None, None  # Added imei and iccid as None
        try:
            line = ser.readline().decode('utf-8', errors='replace').strip()
            if line:
                save_to_log(log_file_path, line)
            if new_keyword in line:
                match_csq = re.search(rf'{re.escape(new_keyword)}\s+(\d+)', line)
                if match_csq:
                    numeric_data_associated_with_csq = match_csq.group(1)
                    break
        except UnicodeDecodeError as e:
            print(f"UnicodeDecodeError: {e}")
            continue
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            break

    if not numeric_data_associated_with_csq:
        numeric_data_associated_with_csq = "0"  # Default value

    df6 = pd.DataFrame({'csq': [numeric_data_associated_with_csq]})
    return df6


def execute_airtel_commands1(ser):
    try:
        time.sleep(1)
        ser.write(b'GSM AT+QSTK=1,1,300')
        time.sleep(0.5)
        ser.write(b'GSM AT+CRSM=176,28486,0,0,17')
        time.sleep(0.5)
        ser.write(b'GSM AT+QSTKGI=37')
        time.sleep(0.5)
        ser.write(b'GSM AT+QSTKRSP=37,0')
        time.sleep(0.5)
        ser.write(b'GSM AT+QSTKRSP=253,0,128')
        time.sleep(0.5)
        ser.write(b'GSM AT+QSTKRSP=36,0,2')
        time.sleep(0.5)
        ser.write(b'GSM AT+QSTKGI=36')
        time.sleep(0.5)
        ser.write(b'GSM AT+QSTKRSP=36,0,22')
        time.sleep(0.5)
        print("commands executed for Airtel Switching....")
        # ser.write(b'*SET#SWNW#1#')
        non_blocking_wait(30, ser, log_file_path)
    except Exception as e:
        print(f"Error in execute_airtel_commands1: {e}")


def extract_data_from_program5(ser, stop_event, operator=None):
    # Define the base keyword
    base_keyword = 'INFO:  [NET] GSM_TX'

    ser.write(b'*SET#LOGFLTR#65535#')

    # Function to wait for the login packet
    def wait_for_login_packet(timeout_duration):
        data_associated_with_keyword5 = ""
        timeout = time.time() + timeout_duration
        while time.time() < timeout:
            if stop_event.is_set():
                ser.close()
                return "STOPPED"
            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                save_to_log(log_file_path, line)
                if base_keyword in line and " |55AA," in line:
                    match = re.search(rf'{re.escape(base_keyword)}\((\d+)\): (.+)$', line)
                    if match:
                        data_associated_with_keyword5 = match.group(2)
                        return data_associated_with_keyword5
            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")
        return data_associated_with_keyword5

    # First attempt to get login packet
    print("Attempt 1: Waiting for login packet for 4 minutes...")
    data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

    if data_associated_with_keyword5:
        print("Login packet found.")
        return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})

    # Reset the device if login packet not found
    print("Login packet not found in Attempt 1. *SET#CRST#1# Resetting the device...")
    ser.write(b'*SET#CRST#1#')
    non_blocking_wait(30, ser, log_file_path)

    # If operator is BSNL, try for login packet with retries
    if operator == "BSNL":
        print("BSNL operator detected. Will retry 2 times for login packet...")

        for retry in range(2):  # 2 retries for BSNL
            print(f"BSNL Retry {retry + 1}/2: Waiting for login packet for 4 minutes...")
            data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

            if data_associated_with_keyword5:
                print(f"Login packet found on BSNL retry {retry + 1}")
                return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})
            else:
                if retry < 1:  # If not last retry, wait a bit before next attempt
                    print(f"Login packet not found on BSNL retry {retry + 1}. Waiting 2 seconds before next retry...")
                    time.sleep(2)

        print("Login packet not found after 2 BSNL retries.")

    # If operator is AIRTEL, just try login packet once more
    elif operator == "AIRTEL":
        print("AIRTEL operator detected. Making one more attempt for login packet...")
        data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

        if data_associated_with_keyword5:
            print("Login packet found on AIRTEL")
            return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})
        else:
            print("Login packet not found on AIRTEL")

    else:
        print(f"Operator: {operator}. Making one final attempt for login packet...")
        data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

        if data_associated_with_keyword5:
            print("Login packet found on final attempt")
            return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})

    print("Login packet not found in all attempts. Stopping execution.")
    return pd.DataFrame({'Login Packets': ['Not found']})


def extract_data_from_program7(ser, stop_event):
    time.sleep(5)  # Initial delay before starting the process
    attempts = 4  # Number of attempts
    attempt_duration = 15  # Duration for each attempt in seconds

    for attempt in range(attempts):
        if stop_event.is_set():
            ser.close()
            return "STOPPED"

        print(f"Attempt {attempt + 1}/{attempts}: Sending GSM AT+CIMI command.")
        ser.write(b'GSM AT+CIMI')
        start_time = time.time()
        new_keywords = [
            'INFO:  [NET] GSM_Rx(25): |',
            'INFO:  [NET] GSM_Rx(31): |',
            'INFO:  [NET] GSM_Rx(33): |'
        ]
        numeric_data_associated_with_GSM = None
        capture_next_line = False

        while True:
            if stop_event.is_set():
                ser.close()
                return "STOPPED"

            try:
                if time.time() - start_time > attempt_duration:
                    print(f"Attempt {attempt + 1} timed out.")
                    break

                line = ser.readline().decode('utf-8', errors='replace').strip()
                save_to_log(log_file_path, line)
                if not line:
                    continue
                if any(keyword in line for keyword in new_keywords):
                    capture_next_line = True
                elif capture_next_line:
                    numeric_data_match = re.search(r'\b404\d+\b', line)
                    if numeric_data_match:
                        numeric_data_associated_with_GSM = numeric_data_match.group(0)
                        break
            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")

        if numeric_data_associated_with_GSM:
            # Determine operator based on IMSI prefix
            if numeric_data_associated_with_GSM.startswith('4046') or numeric_data_associated_with_GSM.startswith(
                    '4045'):
                # print(f"IMSI {numeric_data_associated_with_GSM}")
                print("Wait for Searching operator...")
                operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=15)
                if operator and "BSNL" in operator.upper():
                    print(f"BSNL operator confirmed: {operator}")
                    return "BSNL"

            elif numeric_data_associated_with_GSM.startswith('4041') or numeric_data_associated_with_GSM.startswith(
                    '4040'):
                # print(f"IMSI {numeric_data_associated_with_GSM}")
                print("Switching to BSNL....")
                ser.write(b'*SET#SWNW#1#')  # Switch to BSNL
                time.sleep(5)  # Wait for switch to complete
                # print(f"IMSI {numeric_data_associated_with_GSM} indicates AIRTEL network")
                operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=15)
                if operator and "AIRTEL" in operator.upper():
                    print(f"AIRTEL operator confirmed: {operator}")
                    print("Switching to BSNL....")
                    ser.write(b'*SET#SWNW#1#')  # Switch to BSNL
                    time.sleep(5)  # Wait for switch to complete
                    new_operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=10)

                    if new_operator and "BSNL" in new_operator.upper():
                        print(f"Successfully switched to BSNL: {new_operator}")
                        return "BSNL"
            else:
                operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=10)
                if operator:
                    return operator
                else:
                    return "UNKNOWN"

    # If all attempts fail, try final operator check
    final_operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=10)

    if final_operator:
        print(f"Final operator found: {final_operator}")
        if "BSNL" in final_operator.upper():
            print("Final check: BSNL detected....")
            return "BSNL"
        else:
            print("No operator found after all attempts")
            return "Not found"
    else:
        print("No operator found after all attempts")
        return "Not found"


def check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=30):
    for retry in range(max_retries):
        if stop_event.is_set():
            return None
        start_time = time.time()
        while time.time() - start_time < timeout_per_attempt:
            if stop_event.is_set():
                return None
            try:
                if ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='replace').strip()
                    save_to_log(log_file_path, line)
                    pattern = r'OPR NM:\s*([A-Za-z0-9\s]+)'
                    match = re.search(pattern, line)
                    if match:
                        operator = match.group(1).strip().rstrip('?')
                        print(f"Operator found: {operator}")
                        if "BSNL" in operator:
                            print("BSNL network detected", operator)
                            return "BSNL"

                        elif "AIRTEL" in operator:
                            print("AIRTEL network detected", operator)
                            return "AIRTEL"  # Return BSNL after attempting switch
                        else:
                            return operator
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error reading operator: {e}")
        if retry < max_retries - 1:
            ser.write(b'GSM AT+COPS?')
            time.sleep(15)
    # print(f"Operator not found after {max_retries} retries")
    return None

def get_operator(ser, stop_event):
    """Helper function to get current operator with retries"""
    max_attempts = 2
    print(f"Operator Checking...")

    for attempt in range(max_attempts):
        if stop_event.is_set():
            return None, None

        ser.write(b'GSM AT+CIMI')
        start_time = time.time()
        new_keywords = [
            'INFO:  [NET] GSM_Rx(25): |',
            'INFO:  [NET] GSM_Rx(31): |',
            'INFO:  [NET] GSM_Rx(33): |'
        ]
        capture_next_line = False

        while True:
            if stop_event.is_set():
                return None, None
            if time.time() - start_time > 30:
                break
            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if line:
                    save_to_log(log_file_path, line)
                if not line:
                    continue

                if any(keyword in line for keyword in new_keywords):
                    capture_next_line = True
                elif capture_next_line:
                    numeric_data_match = re.search(r'\b404\d+\b', line)
                    if numeric_data_match:
                        numeric_data = numeric_data_match.group(0)
                        if numeric_data.startswith('4046') or numeric_data.startswith('4045'):
                            return 'BSNL', numeric_data
                        elif numeric_data.startswith('4041') or numeric_data.startswith('4040'):
                            return 'AIRTEL', numeric_data
                        else:
                            return 'UNKNOWN', numeric_data
            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")
                continue

        # print(f"Operator detection attempt {attempt + 1}/{max_attempts} failed")
        time.sleep(5)
    return None, None


def wait_for_login_packet(ser, stop_event, timeout_duration, attempt_name=""):
    base_keyword = 'INFO:  [NET] GSM_TX'
    data_associated_with_keyword5 = ""
    timeout = time.time() + timeout_duration
    while time.time() < timeout:
        if stop_event.is_set():
            return "STOPPED"
        try:
            line = ser.readline().decode('utf-8', errors='replace').strip()
            save_to_log(log_file_path, line)
            if base_keyword in line and " |55AA," in line:
                match = re.search(rf'{re.escape(base_keyword)}\((\d+)\): (.+)$', line)
                if match:
                    data_associated_with_keyword5 = match.group(2)
                    return data_associated_with_keyword5
        except UnicodeDecodeError as e:
            print(f"UnicodeDecodeError: {e}")
    return "Not found"

def extract_data_from_program5_1(ser, stop_event, operator=None):
    # Define the base keyword
    base_keyword = 'INFO:  [NET] GSM_TX'

    ser.write(b'*SET#LOGFLTR#65535#')

    # Function to wait for the login packet
    def wait_for_login_packet(timeout_duration):
        data_associated_with_keyword5 = ""
        timeout = time.time() + timeout_duration
        while time.time() < timeout:
            if stop_event.is_set():
                ser.close()
                return "STOPPED"
            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                save_to_log(log_file_path, line)
                if base_keyword in line and " |55AA," in line:
                    match = re.search(rf'{re.escape(base_keyword)}\((\d+)\): (.+)$', line)
                    if match:
                        data_associated_with_keyword5 = match.group(2)
                        return data_associated_with_keyword5
            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")
        return data_associated_with_keyword5

    # First attempt to get login packet
    print("Attempt 1: Waiting for login packet for 4 minutes...")
    data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

    if data_associated_with_keyword5:
        print("Login packet found.")
        return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})

    # Reset the device if login packet not found
    print("Login packet not found in Attempt 1. *SET#CRST#1# Resetting the device...")
    ser.write(b'*SET#CRST#1#')
    non_blocking_wait(30, ser, log_file_path)

    # If operator is BSNL, try for login packet with retries
    if operator == "BSNL":
        print("BSNL operator detected. Will retry 2 times for login packet...")

        for retry in range(2):  # 2 retries for BSNL
            print(f"BSNL Retry {retry + 1}/2: Waiting for login packet for 4 minutes...")
            data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

            if data_associated_with_keyword5:
                print(f"Login packet found on BSNL retry {retry + 1}")
                return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})
            else:
                if retry < 1:  # If not last retry, wait a bit before next attempt
                    print(f"Login packet not found on BSNL retry {retry + 1}. Waiting 10 seconds before next retry...")
                    time.sleep(10)

        print("Login packet not found after 2 BSNL retries.")

    # If operator is AIRTEL, just try login packet once more
    elif operator == "AIRTEL":
        print("AIRTEL operator detected. Making one more attempt for login packet...")
        data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

        if data_associated_with_keyword5:
            print("Login packet found on AIRTEL")
            return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})
        else:
            print("Login packet not found on AIRTEL")

    else:
        print(f"Operator: {operator}. Making one final attempt for login packet...")
        data_associated_with_keyword5 = wait_for_login_packet(4 * 60)

        if data_associated_with_keyword5:
            print("Login packet found on final attempt")
            return pd.DataFrame({'Login Packets': [data_associated_with_keyword5]})

    print("Login packet not found in all attempts. Stopping execution.")
    return pd.DataFrame({'Login Packets': ['Not found']})


def extract_data_from_program7_1(ser, stop_event):
    time.sleep(5)  # Initial delay before starting the process
    attempts = 4  # Number of attempts
    attempt_duration = 15  # Duration for each attempt in seconds

    for attempt in range(attempts):
        if stop_event.is_set():
            ser.close()
            return "STOPPED"

        print(f"Attempt {attempt + 1}/{attempts}: Sending GSM AT+CIMI command.")
        ser.write(b'GSM AT+CIMI')
        start_time = time.time()
        new_keywords = [
            'INFO:  [NET] GSM_Rx(25): |',
            'INFO:  [NET] GSM_Rx(31): |',
            'INFO:  [NET] GSM_Rx(33): |'
        ]
        numeric_data_associated_with_GSM = None
        capture_next_line = False

        while True:
            if stop_event.is_set():
                ser.close()
                return "STOPPED"

            try:
                if time.time() - start_time > attempt_duration:
                    print(f"Attempt {attempt + 1} timed out.")
                    break

                line = ser.readline().decode('utf-8', errors='replace').strip()
                save_to_log(log_file_path, line)
                if not line:
                    continue
                if any(keyword in line for keyword in new_keywords):
                    capture_next_line = True
                elif capture_next_line:
                    numeric_data_match = re.search(r'\b404\d+\b', line)
                    if numeric_data_match:
                        numeric_data_associated_with_GSM = numeric_data_match.group(0)
                        break
            except UnicodeDecodeError as e:
                print(f"UnicodeDecodeError: {e}")

        if numeric_data_associated_with_GSM:
            # Determine operator based on IMSI prefix
            if numeric_data_associated_with_GSM.startswith('4046') or numeric_data_associated_with_GSM.startswith(
                    '4045'):
                # print(f"IMSI {numeric_data_associated_with_GSM}")
                print("Switching to AIRTEL....")
                execute_airtel_commands1(ser)
                time.sleep(5)

                operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=15)
                if operator and "BSNL" in operator.upper():
                    print(f"BSNL operator confirmed: {operator}")
                    print("Switching to AIRTEL....")
                    execute_airtel_commands1(ser)
                    time.sleep(5)
                    new_operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=10)
                    if new_operator and "AIRTEL" in new_operator.upper():
                        print(f"Successfully switched to AIRTEL: {new_operator}")
                        return "AIRTEL"

            elif numeric_data_associated_with_GSM.startswith('4041') or numeric_data_associated_with_GSM.startswith(
                    '4040'):
                # print(f"IMSI {numeric_data_associated_with_GSM}")
                print("Wait For Searching Operator...")
                operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=15)
                if operator and "AIRTEL" in operator.upper():
                    print(f"AIRTEL operator confirmed: {operator}")
                    return "AIRTEL"
            else:
                operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=10)
                if operator:
                    return operator
                else:
                    return "UNKNOWN"

    # If all attempts fail, try final operator check
    final_operator = check_and_get_operator(ser, stop_event, max_retries=3, timeout_per_attempt=10)

    if final_operator:
        print(f"Final operator found: {final_operator}")
        if "AIRTEL" in final_operator.upper():
            print("Final check: AIRTEL detected....")
            return "AIRTEL"
        else:
            print("No operator found after all attempts")
            return "Not found"
    else:
        print("No operator found after all attempts")
        return "Not found"

def stop_program(selected_device, stop_event, operator_name, qa_name):
    with serial.Serial(selected_device, 115200, timeout=1) as ser:
        ser.close()

start_button_press_cnt = 0
ser1 = 0
def is_file_open(filepath, max_retries=3, delay=1):
    """Check if file is open with retry mechanism"""
    import time

    for attempt in range(max_retries):
        try:
            # Try to open file in exclusive mode
            with open(filepath, 'r+b'):
                pass
            return False
        except (IOError, PermissionError):
            if attempt < max_retries - 1:
                print(f"File is open (attempt {attempt + 1}/{max_retries}), waiting {delay} seconds...")
                time.sleep(delay)
            else:
                return True
    return False

def clean_ansi_codes(text):
    """Remove ANSI escape sequences from text"""
    if isinstance(text, str):
        # Pattern to match ANSI escape sequences (color codes, formatting, etc.)
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        return ansi_escape.sub('', text)
    return text

def clean_dataframe_ansi_codes(df):
    """Clean all string columns in a dataframe from ANSI codes"""
    if df is None or df.empty:
        return df
    df_clean = df.copy()
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            df_clean[col] = df_clean[col].apply(lambda x: clean_ansi_codes(x) if isinstance(x, str) else x)
    return df_clean


def combine_and_save_dataframes(selected_device, stop_event, operator_name, qa_name, qr_code_value, flag=None):
    global start_button_press_cnt
    global ser1
    global subfolder_path, current_date

    if stop_event.is_set():
        print("Stop event detected before starting")
        return "STOPPED", 0, "False", "False", None, None

    df_combined_final_path = os.path.join(subfolder_path, f"Exe_{current_date}.xlsx")
    # Check if Excel file exists and is open
    if os.path.exists(df_combined_final_path):
        if is_file_open(df_combined_final_path):
            messagebox.showerror("File Access Error",
                                 f"Cannot access Excel file:\n{df_combined_final_path}\n"
                                 "Please close the file if it's open in Excel and try again.")
            return "ERROR", 0, "False", "False", None, None
    try:
        df_combined_final = pd.read_excel(df_combined_final_path, engine='openpyxl')
        serial_number = len(df_combined_final) + 1
        data_rows = df_combined_final.to_dict('records')
    except FileNotFoundError:
        df_combined_final = pd.DataFrame()
        serial_number = 1
        data_rows = []

    start_button_press_cnt = 0
    start_button_press_cnt += 1

    if start_button_press_cnt == 1:
        ser = serial.Serial(selected_device, 115200, timeout=1)
        ser1 = ser
        try:
            if stop_event.is_set():
                ser.close()
                return "STOPPED", 0, "False", "False", None, None

            start_time = time.time()
            print("Writing initial commands...")
            write_initial_commands(ser, stop_event)
            df1 = extract_data_from_program1(ser)  # Date and time
            df3 = extract_data_from_program3(ser)
            df11, _, _,_,_,_ = extract_emmc_manufacturer_from_serial(ser, stop_event)
            df4 = extract_data_from_program4(ser, stop_event)  # Certificates
            operator = extract_data_from_program7(ser, stop_event)
            if operator == "BSNL":
                df7 = pd.DataFrame({'OPERATOR': [operator]})
            else:
                df7 = pd.DataFrame({'OPERATOR': ['Not found']})
            df5 = extract_data_from_program5(ser, stop_event, operator)  # Pass operator for retry logic
            df12, fix_quality = extract_data_from_program12(ser, stop_event)  # GPS data
            df6 = extract_data_from_program6(ser, stop_event)
            df9 = run_extract_analog_status_in_thread(ser, stop_event)
            df8, mode_val = extract_data_from_program8(ser, stop_event)  # check modem network registration
            print(f"mode_val: {mode_val}")  # Debug print
            print(f"Operator detected: {operator}")
            print(f"Fix Quality: {fix_quality}")
            write_final_commands(ser, stop_event)
            print("Writing final commands...")
            imei, iccid = extract_gsm_data_from_serial_regex(ser, stop_event)
            print("actual imei & iccid", imei, iccid)

            end_time = time.time()
            execution_time = end_time - start_time
            execution_time = round(execution_time, 2)
            df_execution_time = pd.DataFrame(
                [{"Execution Time": str(execution_time)}])

            # Convert all dataframes to string type
            df1 = df1.astype(str)
            df3 = df3.astype(str)
            df4 = df4.astype(str)
            df7 = df7.astype(str)

            # Ensure df5 exists before converting
            if df5 is not None and not df5.empty:
                df5 = df5.astype(str)
            else:
                df5 = pd.DataFrame({'Login Packets': ['Not found']})

            df6 = df6.astype(str)
            df8 = df8.astype(str) #df11
            df11 = df11.astype(str)
            df9 = df9.astype(str)

            if df12 is not None and not df12.empty:
                df12 = df12.astype(str)
            else:
                df12 = pd.DataFrame()

            # Clean ANSI escape sequences from all dataframes
            df1 = clean_dataframe_ansi_codes(df1)
            df3 = clean_dataframe_ansi_codes(df3)
            df4 = clean_dataframe_ansi_codes(df4)
            df7 = clean_dataframe_ansi_codes(df7)
            df5 = clean_dataframe_ansi_codes(df5)
            df6 = clean_dataframe_ansi_codes(df6)
            df8 = clean_dataframe_ansi_codes(df8)
            df11 = clean_dataframe_ansi_codes(df11)
            df9 = clean_dataframe_ansi_codes(df9)
            if not df12.empty:
                df12 = clean_dataframe_ansi_codes(df12)

            # Extract default parameters
            default_parameters = df3.iloc[0].to_dict()
            excluded_columns = ['Serial Number', 'Date', 'Current Time', 'OPERATOR', 'csq', 'Execution Time',
                                'Login Packets']

            # Combine DataFrames - include df7 (operator) now
            dfs_to_concat = [df1, df_execution_time, df3, df4, df9, df7, df5, df6, df8, df11]
            if not df12.empty:
                dfs_to_concat.append(df12)

            df_combined = pd.concat(dfs_to_concat, axis=1)
            df_combined = df_combined.astype(str)
            df_combined = clean_dataframe_ansi_codes(df_combined)

            condition_met_DO1 = str(df9.iloc[0]['DO1 status'])
            condition_met_DO2 = str(df9.iloc[0]['DO2 status'])
            data_row = {"Serial Number": str(serial_number)}
            data_row["QR Code"] = str(qr_code_value)
            data_row.update(df_combined.iloc[0].to_dict())

            # Safely check login packet
            if df5 is not None and not df5.empty and 'Login Packets' in df5.columns:
                login_packet_found = 'Not found' not in str(df5.iloc[0]['Login Packets'])
            else:
                login_packet_found = False

            default_parameters_match = all(str(data_row[key]) == str(default_parameters.get(key, None)) for key in
                                           [k for k in data_row.keys() if k not in excluded_columns])

            default_parameter_status = df3.iloc[0]['default parameter']

            # Check operator status
            operator_found = operator and operator != "Not found" and operator != "STOPPED"
            is_bsnl_operator = (operator == "BSNL" or (operator and "BSNL" in operator.upper()))

            print(f"Operator Status - Found: {operator_found}, Is BSNL: {is_bsnl_operator}, Operator: {operator}")
            print(f"Login Packet Found: {login_packet_found}")
            print(f"Default Parameter Status: {default_parameter_status}")

            # Enhanced PASS/FAIL conditions including operator check
            if (default_parameter_status == "available" and
                    login_packet_found and
                    condition_met_DO1 == "True" and
                    condition_met_DO2 == "True" and
                    fix_quality != "0" and
                    fix_quality is not None and
                    mode_val != 2 and mode_val != 1 and mode_val != 3 and
                    operator_found and is_bsnl_operator):
                result = "PASS"
                reason = "Passed all the conditions"
            else:
                result = "FAIL"
                if default_parameter_status == "unavailable":
                    reason = "Default parameters are unavailable"
                elif not operator_found:
                    reason = "Operator Not found"
                elif not is_bsnl_operator:
                    reason = f"Operator is Not BSNL)"
                elif not login_packet_found:
                    reason = "Login packet not found"
                elif condition_met_DO1 == "False":
                    reason = "DO1 condition false"
                elif condition_met_DO2 == "False":
                    reason = "DO2 condition false"
                elif fix_quality == "0" or fix_quality is None:
                    reason = "GPS Not Fix"
                elif mode_val == 1:
                    reason = f"Mode value is {mode_val}, expected 0"
                elif mode_val == 2:
                    reason = f"Mode value is {mode_val}, expected 0"
                elif mode_val == 3:
                    reason = f"Mode value is {mode_val}, expected 0"
                elif mode_val is None:
                    reason = "Mode value is None"
                else:
                    reason = f"Unknown reason for FAIL. Default: {default_parameter_status}, Login: {login_packet_found}, DO1: {condition_met_DO1}, DO2: {condition_met_DO2}, Fix: {fix_quality}, Mode: {mode_val}, Operator: {operator}"

            # Append QA and Operator names to the DataFrame
            # data_row["Mode Value"] = str(mode_val) if mode_val is not None else "None"
            data_row["GPS Fix/Unfix"] = str(fix_quality) if fix_quality is not None else "None"
            # data_row["Detected Operator"] = str(operator) if operator else "None"
            data_row["Screwing Station"] = "PASS"
            data_row["Operator Name"] = str(operator_name)
            data_row["QA Name"] = str(qa_name)
            data_row["Execution Time"] = str(execution_time)
            data_row["Result"] = result
            data_row["Failure Reason"] = reason
            data_rows.append(data_row)
            df_combined_final = pd.DataFrame(data_rows)
            df_combined_final = df_combined_final.astype(str)
            df_combined_final = clean_dataframe_ansi_codes(df_combined_final)

            # Save to Excel with coloring for FAIL results
            df_combined_final.to_excel(df_combined_final_path, index=False, engine='openpyxl')

            # Apply color to Result column based on PASS/FAIL
            try:
                from openpyxl import load_workbook
                from openpyxl.styles import PatternFill, Font, Alignment

                # Load the workbook
                wb = load_workbook(df_combined_final_path)
                ws = wb.active

                # Define colors
                red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
                green_fill = PatternFill(start_color="00FF00", end_color="00FF00", fill_type="solid")
                white_font = Font(color="FFFFFF", bold=True)
                black_font = Font(color="000000", bold=True)

                # Find column indices
                headers = []
                for col_idx in range(1, ws.max_column + 1):
                    headers.append(ws.cell(row=1, column=col_idx).value)

                try:
                    result_col = headers.index("Result") + 1
                except ValueError:
                    print("Result column not found for coloring")
                    return result, serial_number, condition_met_DO1, condition_met_DO2, imei, iccid

                # Apply coloring to Result column only
                for row_idx in range(2, ws.max_row + 1):
                    result_cell = ws.cell(row=row_idx, column=result_col)

                    # Center align the Result cell
                    result_cell.alignment = Alignment(horizontal='center', vertical='center')

                    if result_cell.value == "FAIL":
                        # Color the Result cell red with white text
                        result_cell.fill = red_fill
                        result_cell.font = white_font
                    elif result_cell.value == "PASS":
                        # Color the Result cell green with black text
                        result_cell.fill = green_fill
                        result_cell.font = black_font

                # Save the workbook
                wb.save(df_combined_final_path)

            except Exception as e:
                print(f"Error applying color to Excel: {e}")
                # Continue even if coloring fails

            return result, serial_number, condition_met_DO1, condition_met_DO2, imei, iccid

        except KeyboardInterrupt:
            if 'ser' in locals() and ser and ser.is_open:
                ser.close()
            return "STOPPED", 0, "False", "False", None, None
        except Exception as e:
            print(f"Error in combine_and_save_dataframes main block: {e}")
            import traceback
            traceback.print_exc()
            if 'ser' in locals() and ser and ser.is_open:
                ser.close()
            return "ERROR", 0, "False", "False", None, None
        finally:
            if 'ser' in locals() and ser and ser.is_open:
                ser.close()
            start_button_press_cnt = 0
    else:
        start_button_press_cnt = 0
        return "STOPPED", 0, "False", "False", None, None


def combine_and_save_dataframes1(selected_device, stop_event, operator_name, qa_name, qr_code_value, flag=None):
    global start_button_press_cnt
    global ser1
    global subfolder_path, current_date

    if stop_event.is_set():
        print("Stop event detected before starting")
        return "STOPPED", 0, "False", "False", None, None

    df_combined_final_path = os.path.join(subfolder_path, f"Exe_{current_date}.xlsx")
    # Check if Excel file exists and is open
    if os.path.exists(df_combined_final_path):
        if is_file_open(df_combined_final_path):
            messagebox.showerror("File Access Error",
                                 f"Cannot access Excel file:\n{df_combined_final_path}\n"
                                 "Please close the file if it's open in Excel and try again.")
            return "ERROR", 0, "False", "False", None, None
    try:
        df_combined_final = pd.read_excel(df_combined_final_path, engine='openpyxl')
        serial_number = len(df_combined_final) + 1
        data_rows = df_combined_final.to_dict('records')
    except FileNotFoundError:
        df_combined_final = pd.DataFrame()
        serial_number = 1
        data_rows = []

    start_button_press_cnt = 0
    start_button_press_cnt += 1

    if start_button_press_cnt == 1:
        ser = serial.Serial(selected_device, 115200, timeout=1)
        ser1 = ser
        try:
            if stop_event.is_set():
                ser.close()
                return "STOPPED", 0, "False", "False", None, None

            start_time = time.time()
            print("Writing initial commands...")
            write_initial_commands(ser, stop_event)

            df1 = extract_data_from_program1(ser)  # Date and time
            df3 = extract_data_from_program3(ser)  # Keywords
            df11, _, _,_,_,_ = extract_emmc_manufacturer_from_serial(ser, stop_event)
            df4 = extract_data_from_program4(ser, stop_event)  # Certificates
            operator = extract_data_from_program7_1(ser, stop_event)  # OP
            if operator == "AIRTEL":
                df7 = pd.DataFrame({'OPERATOR': [operator]})
            else:
                df7 = pd.DataFrame({'OPERATOR': ['Not found']})

            df5 = extract_data_from_program5_1(ser, stop_event, operator)  # Login
            df12, fix_quality = extract_data_from_program12(ser, stop_event)  # GPS data
            df6 = extract_data_from_program6(ser, stop_event)
            df9 = run_extract_analog_status_in_thread(ser, stop_event)
            df8, mode_val = extract_data_from_program8(ser, stop_event)  # check modem network registration

            print(f"mode_val: {mode_val}")  # Debug print
            print(f"Operator detected: {operator}")
            print(f"Fix Quality: {fix_quality}")

            write_final_commands(ser, stop_event)
            print("Writing final commands...")
            imei, iccid = extract_gsm_data_from_serial_regex(ser, stop_event)
            print("actual imei & iccid", imei, iccid)

            end_time = time.time()
            execution_time = end_time - start_time
            execution_time = round(execution_time, 2)
            df_execution_time = pd.DataFrame(
                [{"Execution Time": str(execution_time)}])

            # Convert all dataframes to string type
            df1 = df1.astype(str)
            df3 = df3.astype(str)
            df4 = df4.astype(str)
            df7 = df7.astype(str)

            # Ensure df5 exists before converting
            if df5 is not None and not df5.empty:
                df5 = df5.astype(str)
            else:
                df5 = pd.DataFrame({'Login Packets': ['Not found']})

            df6 = df6.astype(str)
            df8 = df8.astype(str)
            df11 = df11.astype(str)
            df9 = df9.astype(str)

            if df12 is not None and not df12.empty:
                df12 = df12.astype(str)
            else:
                df12 = pd.DataFrame()

            # Clean ANSI escape sequences from all dataframes
            df1 = clean_dataframe_ansi_codes(df1)
            df3 = clean_dataframe_ansi_codes(df3)
            df4 = clean_dataframe_ansi_codes(df4)
            df7 = clean_dataframe_ansi_codes(df7)
            df5 = clean_dataframe_ansi_codes(df5)
            df6 = clean_dataframe_ansi_codes(df6)
            df8 = clean_dataframe_ansi_codes(df8)
            df11 = clean_dataframe_ansi_codes(df11)
            df9 = clean_dataframe_ansi_codes(df9)
            if not df12.empty:
                df12 = clean_dataframe_ansi_codes(df12)

            # Extract default parameters
            default_parameters = df3.iloc[0].to_dict()
            excluded_columns = ['Serial Number', 'Date', 'Current Time', 'OPERATOR', 'csq', 'Execution Time',
                                'Login Packets']

            # Combine DataFrames
            dfs_to_concat = [df1, df_execution_time, df3, df4, df9, df7, df5, df6, df8, df11]
            if not df12.empty:
                dfs_to_concat.append(df12)

            df_combined = pd.concat(dfs_to_concat, axis=1)
            df_combined = df_combined.astype(str)
            df_combined = clean_dataframe_ansi_codes(df_combined)

            condition_met_DO1 = str(df9.iloc[0]['DO1 status'])
            condition_met_DO2 = str(df9.iloc[0]['DO2 status'])
            data_row = {"Serial Number": str(serial_number)}
            data_row["QR Code"] = str(qr_code_value)
            data_row.update(df_combined.iloc[0].to_dict())

            # Safely check login packet
            if df5 is not None and not df5.empty and 'Login Packets' in df5.columns:
                login_packet_found = 'Not found' not in str(df5.iloc[0]['Login Packets'])
            else:
                login_packet_found = False

            default_parameters_match = all(str(data_row[key]) == str(default_parameters.get(key, None)) for key in
                                           [k for k in data_row.keys() if k not in excluded_columns])

            default_parameter_status = df3.iloc[0]['default parameter']

            # Check operator status for AIRTEL
            operator_found = operator and operator != "Not found" and operator != "STOPPED"
            is_airtel_operator = (operator == "AIRTEL" or (operator and "AIRTEL" in operator.upper()))

            print(
                f"Operator Status - Found: {operator_found}, Is AIRTEL: {is_airtel_operator}, Operator: {operator}")
            print(f"Login Packet Found: {login_packet_found}")
            print(f"Default Parameter Status: {default_parameter_status}")

            # PASS/FAIL conditions for AIRTEL
            if (default_parameter_status == "available" and
                    login_packet_found and
                    condition_met_DO1 == "True" and
                    condition_met_DO2 == "True" and
                    fix_quality != "0" and
                    fix_quality is not None and
                    mode_val != 2 and mode_val != 1 and mode_val != 3 and
                    operator_found and is_airtel_operator):
                result = "PASS"
                reason = "Passed all the conditions"
            else:
                result = "FAIL"
                if default_parameter_status == "unavailable":
                    reason = "Default parameters are unavailable"
                elif not operator_found:
                    reason = f"Operator not found"
                elif not is_airtel_operator:
                    reason = f"Operator is not AIRTEL"
                elif not login_packet_found:
                    reason = "Login packet not found"
                elif condition_met_DO1 == "False":
                    reason = "DO1 condition false"
                elif condition_met_DO2 == "False":
                    reason = "DO2 condition false"
                elif fix_quality == "0" or fix_quality is None:
                    reason = "GPS Not Fix"
                elif mode_val == 1:
                    reason = f"Mode value is {mode_val}, expected 0"
                elif mode_val == 2:
                    reason = f"Mode value is {mode_val}, expected 0"
                elif mode_val == 3:
                    reason = f"Mode value is {mode_val}, expected 0"
                elif mode_val is None:
                    reason = "Mode value is None"
                else:
                    reason = f"Unknown reason for FAIL. Default: {default_parameter_status}, Login: {login_packet_found}, DO1: {condition_met_DO1}, DO2: {condition_met_DO2}, Fix: {fix_quality}, Mode: {mode_val}, Operator: {operator}"

            data_row["GPS Fix/Unfix"] = str(fix_quality) if fix_quality is not None else "None"
            # data_row["Detected Operator"] = str(operator) if operator else "None"
            data_row["Screwing Station"] = "PASS"
            data_row["Operator Name"] = str(operator_name)
            data_row["QA Name"] = str(qa_name)
            data_row["Execution Time"] = str(execution_time)
            data_row["Result"] = result
            data_row["Failure Reason"] = reason
            data_rows.append(data_row)
            df_combined_final = pd.DataFrame(data_rows)
            df_combined_final = df_combined_final.astype(str)
            df_combined_final = clean_dataframe_ansi_codes(df_combined_final)

            df_combined_final.to_excel(df_combined_final_path, index=False, engine='openpyxl')
            try:
                from openpyxl import load_workbook
                from openpyxl.styles import PatternFill, Font, Alignment

                # Load the workbook
                wb = load_workbook(df_combined_final_path)
                ws = wb.active

                # Define colors
                red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
                green_fill = PatternFill(start_color="00FF00", end_color="00FF00", fill_type="solid")
                white_font = Font(color="FFFFFF", bold=True)
                black_font = Font(color="000000", bold=True)

                # Find column indices
                headers = []
                for col_idx in range(1, ws.max_column + 1):
                    headers.append(ws.cell(row=1, column=col_idx).value)

                try:
                    result_col = headers.index("Result") + 1
                except ValueError:
                    print("Result column not found for coloring")
                    return result, serial_number, condition_met_DO1, condition_met_DO2, imei, iccid

                # Apply coloring to Result column only
                for row_idx in range(2, ws.max_row + 1):
                    result_cell = ws.cell(row=row_idx, column=result_col)

                    # Center align the Result cell
                    result_cell.alignment = Alignment(horizontal='center', vertical='center')

                    if result_cell.value == "FAIL":
                        # Color the Result cell red with white text
                        result_cell.fill = red_fill
                        result_cell.font = white_font
                    elif result_cell.value == "PASS":
                        # Color the Result cell green with black text
                        result_cell.fill = green_fill
                        result_cell.font = black_font

                # Save the workbook
                wb.save(df_combined_final_path)

            except Exception as e:
                print(f"Error applying color to Excel: {e}")
                # Continue even if coloring fails

            return result, serial_number, condition_met_DO1, condition_met_DO2, imei, iccid

        except KeyboardInterrupt:
            if 'ser' in locals() and ser and ser.is_open:
                ser.close()
            return "STOPPED", 0, "False", "False", None, None
        except Exception as e:
            import traceback
            traceback.print_exc()
            if 'ser' in locals() and ser and ser.is_open:
                ser.close()
            return "ERROR", 0, "False", "False", None, None
        finally:
            if 'ser' in locals() and ser and ser.is_open:
                ser.close()
            start_button_press_cnt = 0
    else:
        start_button_press_cnt = 0
        return "STOPPED", 0, "False", "False", None, None


def combine_and_save_QR(operator_name, qa_name, qr_code_value, api_response_data, result_status, failure_reason=None):
    print("api_response_data", api_response_data)
    global subfolder_path, current_date
    df_combined_final_path = os.path.join(subfolder_path, f"Exe_{current_date}.xlsx")
    try:
        df_combined_final = pd.read_excel(df_combined_final_path, engine='openpyxl')
        serial_number = len(df_combined_final) + 1
        existing_columns = df_combined_final.columns.tolist()
        data_rows = df_combined_final.to_dict('records')

    except FileNotFoundError:
        print("Excel file not found, creating new one")
        df_combined_final = pd.DataFrame()
        serial_number = 1
        existing_columns = []
        data_rows = []

    except Exception as e:
        print(f"Error reading Excel file: {e}")
        df_combined_final = pd.DataFrame()
        serial_number = 1
        existing_columns = []
        data_rows = []

    # Create data row with ALL possible columns to match your test results structure
    data_row = {
        "Serial Number": str(serial_number),
        "QR Code": str(qr_code_value),
        "Date": datetime.now().strftime('%Y-%m-%d'),
        "Current Time": datetime.now().strftime('%H:%M:%S'),
        "Execution Time": "0",
        "ais.ip:port(CHTP)": " ",
        "aepl.ip1.port(CIP1)": " ",
        "aepl.ip1.port(CIP2)": " ",
        "tml.ip:port": " ",
        "tml.ip:port(CIP3)": " ",
        "tml.pvtSec (Sending) (TNPIN)60": " ",
        "tml.pvtSec (loging)(TLPIN)5": " ",
        "tml.canSec(sending)(CPIN)": " ",
        "tml.canSec(loging) (CLPIN)30": " ",
        "TDPS (value=0)": " ",
        "No of fuel tank (NOFT)(value=1)": " ",
        "AFT autodetection flag(AFTAD)(value=0)": " ",
        "AFT Enable(AFT) value=0": " ",
        "tml.sslConfig": " ",
        "Software Version": " ",
        "Hardware Version": " ",
        "ECUID": " ",
        "ICCID": " ",
        "IMEI": " ",
        "default parameter": "unavailable",
        "Hardware Details": " ",
        "Software Details": " ",
        "QA Certificates on eMMC": " ",
        "DO1 status": " ",
        "DO2 status": " ",
        "OPERATOR": " ",
        "Login Packets": " ",
        "csq": " ",
        "Mode Value": " ",
        "FIX Quality": " ",
        "Screwing Station": "FAIL" if result_status == "FAIL" else "PASS",
        "Operator Name": str(operator_name) if operator_name else "N/A",
        "QA Name": str(qa_name) if qa_name else "N/A",
        "Result": result_status,
        "Failure Reason": " " if result_status == "PASS" else str(failure_reason)
    }

    # If there are existing columns that we haven't included, add them with N/A
    for column in existing_columns:
        if column not in data_row:
            data_row[column] = " "

    # Add the new row
    data_rows.append(data_row)
    df_combined_final = pd.DataFrame(data_rows)
    if existing_columns:
        new_columns = [col for col in df_combined_final.columns if col not in existing_columns]
        column_order = existing_columns + new_columns
        df_combined_final = df_combined_final[column_order]

    # Save to Excel
    df_combined_final.to_excel(df_combined_final_path, index=False, engine='openpyxl')

    # Apply colors to Result, Failure Reason, and Screwing Station columns based on PASS/FAIL
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import PatternFill, Font, Alignment

        # Load the workbook
        wb = load_workbook(df_combined_final_path)
        ws = wb.active

        # Define colors
        red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
        green_fill = PatternFill(start_color="00FF00", end_color="00FF00", fill_type="solid")
        white_font = Font(color="FFFFFF", bold=True)
        black_font = Font(color="000000", bold=True)
        light_red_fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
        light_green_fill = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")

        # Find column indices
        headers = []
        for col_idx in range(1, ws.max_column + 1):
            headers.append(ws.cell(row=1, column=col_idx).value)

        try:
            result_col = headers.index("Result") + 1
            reason_col = headers.index("Failure Reason") + 1
            screwing_col = headers.index("Screwing Station") + 1 if "Screwing Station" in headers else None
        except ValueError:
            print("Required columns not found for coloring")
            return True, serial_number

        # Apply coloring to rows
        for row_idx in range(2, ws.max_row + 1):
            result_cell = ws.cell(row=row_idx, column=result_col)
            reason_cell = ws.cell(row=row_idx, column=reason_col)

            # Center align the Result cell
            result_cell.alignment = Alignment(horizontal='center', vertical='center')

            if result_cell.value == "FAIL":
                # Color the Result cell red with white text
                result_cell.fill = red_fill
                result_cell.font = white_font

                # Color the failure reason cell red with white text
                reason_cell.fill = red_fill
                reason_cell.font = white_font

                # Color the entire row light red for better visibility
                for col_idx in range(1, ws.max_column + 1):
                    if col_idx != result_col and col_idx != reason_col:  # Skip Result and Reason columns as they already have dark red
                        cell = ws.cell(row=row_idx, column=col_idx)
                        cell.fill = light_red_fill

                # Also color Screwing Station cell if it exists
                if screwing_col:
                    screwing_cell = ws.cell(row=row_idx, column=screwing_col)
                    screwing_cell.fill = red_fill
                    screwing_cell.font = white_font

            elif result_cell.value == "PASS":
                # Color the Result cell green with black text
                result_cell.fill = green_fill
                result_cell.font = black_font

                # Color the failure reason cell green with black text
                reason_cell.fill = green_fill
                reason_cell.font = black_font

                # Color the entire row light green for better visibility
                for col_idx in range(1, ws.max_column + 1):
                    if col_idx != result_col and col_idx != reason_col:  # Skip Result and Reason columns as they already have dark green
                        cell = ws.cell(row=row_idx, column=col_idx)
                        cell.fill = light_green_fill
                if screwing_col:
                    screwing_cell = ws.cell(row=row_idx, column=screwing_col)
                    screwing_cell.fill = green_fill
                    screwing_cell.font = black_font
        wb.save(df_combined_final_path)
    except Exception as e:
        print(f"Error applying color to Excel in combine_and_save_QR: {e}")
        import traceback
        traceback.print_exc()
    return True, serial_number


def combine_and_save_QR1(failure_reason=""):
    """Update only the Failure Reason column for the last row in Excel"""
    global subfolder_path, current_date

    excel_path = os.path.join(subfolder_path, f"Exe_{current_date}.xlsx")

    try:
        # Read existing data
        df = pd.read_excel(excel_path, engine='openpyxl')

        # Update only the last row's Failure Reason
        if len(df) > 0:
            # Always update the last row's Failure Reason with the provided reason
            df.at[len(df) - 1, 'Failure Reason'] = str(failure_reason) if failure_reason else ""

            # Determine result status
            if failure_reason:
                df.at[len(df) - 1, 'Result'] = "FAIL"
                print(f"Updated last row (row {len(df)}) with FAIL status and reason: {str(failure_reason)[:100]}...")
            else:
                df.at[len(df) - 1, 'Result'] = "PASS"
                print(f"Updated last row (row {len(df)}) with PASS status")

            # Save back to Excel
            df.to_excel(excel_path, index=False, engine='openpyxl')

            # Apply coloring to the updated row
            try:
                from openpyxl import load_workbook
                from openpyxl.styles import PatternFill, Font, Alignment

                wb = load_workbook(excel_path)
                ws = wb.active

                # Define colors
                red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
                green_fill = PatternFill(start_color="00FF00", end_color="00FF00", fill_type="solid")
                white_font = Font(color="FFFFFF", bold=True)
                black_font = Font(color="000000", bold=True)

                # Find column indices
                headers = []
                for col_idx in range(1, ws.max_column + 1):
                    headers.append(ws.cell(row=1, column=col_idx).value)

                try:
                    result_col = headers.index("Result") + 1
                except ValueError:
                    print("Result column not found")
                    return True

                # Apply coloring to the last row only
                last_row = ws.max_row
                result_cell = ws.cell(row=last_row, column=result_col)
                result_cell.alignment = Alignment(horizontal='center', vertical='center')

                # Color based on result
                if failure_reason:
                    # FAIL case - Red with white text
                    result_cell.fill = red_fill
                    result_cell.font = white_font
                else:
                    # PASS case - Green with black text
                    result_cell.fill = green_fill
                    result_cell.font = black_font

                wb.save(excel_path)

            except Exception as e:
                print(f"Error applying color to Excel: {e}")

            return True
        else:
            print("No data rows found in Excel")
            return False

    except FileNotFoundError:
        print(f"Excel file not found: {excel_path}")
        return False