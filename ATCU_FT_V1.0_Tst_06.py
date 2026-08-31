'''
Copyright 2026-2027 Accolade Electronics Pvt. Ltd

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
version 2 as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

file        ATCU_FT_V1.0_Tst_06.py
brief       This is the source file for the Atcu testing integration

date        25-3-2026
author      Accolade Electronics <www.accoladeelectronics.com>
Developed by   Anjanrav Dhole
'''
from datetime import datetime
import tkinter as tk
from tkinter import PhotoImage, StringVar, scrolledtext, simpledialog
from tkinter import ttk
from tkinter import messagebox
import threading
import queue
import requests
import serial
from PIL import Image, ImageTk
import serial.tools.list_ports
import subprocess
from threading import Event
import sys
import pandas as pd
import os
import time
import openpyxl

from test_04 import combine_and_save_dataframes, combine_and_save_dataframes1, combine_and_save_QR, combine_and_save_QR1

stop_event = Event()
process = None  # Global variable to hold the subprocess object

com_port_var = None
com_port_dropdown = None
start_button = None
stop_button = None
output_text = None
output_queue = queue.Queue()
selected_device = None
stopwatch_var = None
stopwatch_running = False
baudrate_var = None
baudrate_dropdown = None
airtel_authenticated = False  # Track Airtel authentication status
extraction_thread = None  # Store the extraction thread


def resource_path(relative_path):
    """ Get the absolute path to the resource in the executable or when running the script. """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# Use resource_path to load the image
image_file_path = resource_path("accolade-logo.png")


class RedirectText:
    def __init__(self, queue, text_widget):
        self.queue = queue
        self.text_widget = text_widget

    def write(self, string):
        self.queue.put(string)

    def flush(self):
        # Nothing special needed, but must exist
        pass


class Stopwatch:
    def __init__(self, stopwatch_var):
        self.stopwatch_var = stopwatch_var
        self.start_time = None
        self.stop_time = None
        self.elapsed_time = None
        self.update_interval = 100  # Update interval in milliseconds

    def start(self):
        self.start_time = datetime.now()
        def update():
            if self.start_time:
                elapsed = datetime.now() - self.start_time
                self.elapsed_time = str(elapsed).split('.')[0]  # Format as HH:MM:SS
                self.stopwatch_var.set(self.elapsed_time)
                output_text.after(self.update_interval, update)
        update()

    def stop(self):
        self.stop_time = datetime.now()
        if self.start_time:
            self.elapsed_time = str(self.stop_time - self.start_time).split('.')[0]
            self.stopwatch_var.set(self.elapsed_time)
            self.start_time = None


def update_output():
    """Update output text from queue"""
    try:
        while not output_queue.empty():
            output = output_queue.get()
            output_text.insert(tk.END, output)
            output_text.see(tk.END)
    except Exception as e:
        print(f"Error updating output: {e}")
    output_text.after(100, update_output)


def get_connected_devices():
    ports = serial.tools.list_ports.comports()
    devices = [(port.device, port.description) for port in ports]
    return devices


def validate_inputs(com_port_var, baudrate_var, operator_name_entry, qa_name_entry, qr_code):
    """Validate all input fields before starting"""

    if not com_port_var.get():
        messagebox.showerror("Error", "Please select a COM port")
        return False

    selected_device = com_port_var.get().split(" - ")[0]
    baudrate = baudrate_var.get()
    operator_name = operator_name_entry.get()
    qa_name = qa_name_entry.get()
    qr_code_value = qr_code.get()

    if not qr_code_value:
        messagebox.showerror("QR Code", "Please Scan QR code then Proceed")
        return False

    if not selected_device or not operator_name or not qa_name:
        messagebox.showerror("Error", "Please fill all fields")
        return False

    if baudrate != '115200':
        messagebox.showerror("Error", "Please select the correct baudrate (115200)")
        return False

    if not operator_name.isalpha() or not qa_name.isalpha():
        messagebox.showerror("Error",
                             "Please input correct names (only alphabetic characters are allowed).")
        return False
    return True


def reset_colors():
    """Reset DO status circles to red"""
    global do1_status_label, do2_status_label
    try:
        canvas.itemconfig(circle1, fill="red")
        canvas.itemconfig(circle2, fill="red")
        canvas.update()
        print("Resetting colors to red")
    except Exception as e:
        print(f"Error resetting colors: {e}")


def reset_ui_for_next_test():
    """Reset UI elements to allow next test to start"""
    global stopwatch_running, stop_event, start_button, stopwatch, stopwatch_var, output_queue

    # Reset flags
    stopwatch_running = False
    if 'stop_event' in globals() and stop_event:
        stop_event.clear()  # Clear the stop event for next use

    # Reset button
    if 'start_button' in globals() and start_button:
        start_button.config(text="START")

    # Reset DO status circles to red
    try:
        reset_colors()
    except Exception as e:
        print(f"Error calling reset_colors: {e}")

    # Reset stopwatch display to 00:00:00
    if 'stopwatch' in globals() and stopwatch:
        stopwatch.stop()
        if 'stopwatch_var' in globals() and stopwatch_var:
            stopwatch_var.set("00:00:00")

    # Ensure serial port is closed
    try:
        from test_04 import ser1
        if 'ser1' in globals() and ser1 and ser1.is_open:
            ser1.close()
            print("Serial port closed")
    except Exception as e:
        print(f"Error closing serial port: {e}")

    # Clear any remaining data
    if 'output_queue' in globals() and output_queue:
        try:
            output_queue.put("\n--- Ready for next test ---\n")
            root.after(100, qr_code.focus_set)
        except:
            pass

    print("UI reset for next test")


def create_widgets():
    global com_port_var, baudrate_var, com_port_dropdown, stopwatch, start_button, stop_button, output_text, selected_device, stopwatch_var, operator_name_entry, qa_name_entry, qr_code
    global result_display_label, canvas, circle1, circle2, total_count_var, total_count_label, pass_count_var, fail_count_var
    global progress_var, progress_label_var, result_var, reason_var, date_var, time_var, radio_value, root

    # Create root window FIRST
    root = tk.Tk()
    root.title(" ATCU_Final_Testing")
    root.geometry("1300x680")  # Set a fixed size for the utility window

    # Now create Tkinter variables AFTER root window is created
    com_port_var = tk.StringVar()
    baudrate_var = tk.StringVar()
    stopwatch_var = tk.StringVar(value="00:00:00")

    # Initialize count variables
    total_count_var = tk.StringVar(value="0")
    pass_count_var = tk.StringVar(value="Pass Count: 0")
    fail_count_var = tk.StringVar(value="Fail Count: 0")

    def update_total_count():
        """Update total count based on pass and fail counts"""
        try:
            # Extract numeric values from pass and fail count strings
            pass_text = pass_count_var.get()
            fail_text = fail_count_var.get()

            pass_count = int(pass_text.split(": ")[1]) if ": " in pass_text else 0
            fail_count = int(fail_text.split(": ")[1]) if ": " in fail_text else 0

            total = pass_count + fail_count
            total_count_var.set(str(total))
        except Exception as e:
            print(f"Error updating total count: {e}")
            total_count_var.set("0")

    def connect_button_clicked():
        global selected_device
        if com_port_var.get():
            selected_device = com_port_var.get().split(" - ")[0]
            print(f"Selected device: {selected_device}")

    def update_dropdown():
        connected_devices = get_connected_devices()
        com_port_dropdown['values'] = [f"{device[0]} - {device[1]}" for device in connected_devices]
        if connected_devices:
            com_port_dropdown.set('')  # Clear selection

    def on_operator_mode_change():
        """Handle operator mode switch - authentication required for Airtel"""
        global airtel_authenticated
        selected_mode = radio_value.get()
        config = load_config()
        if selected_mode == 2:  # Airtel mode selected
            # Always ask for password when switching to Airtel mode
            entered_password = simpledialog.askstring(
                "Password Required",
                "Enter Airtel activation password:",
                show="*",
                parent=root
            )
            if entered_password is None:
                # Password dialog cancelled, switch back to BSNL
                radio_value.set(1)
                airtel_authenticated = False
                messagebox.showinfo("Mode Changed", "Switched to BSNL Mode")
                print("Password dialog cancelled. Switching back to BSNL mode.")
                return

            AIRTEL_PASSWORD = config.get("AIRTEL_PASSWORD", "")
            if entered_password != AIRTEL_PASSWORD:
                messagebox.showerror("Access Denied", "Incorrect password!")
                radio_value.set(1)  # Switch back to BSNL
                airtel_authenticated = False
                return

            airtel_authenticated = True
            messagebox.showinfo("Success", "Airtel Mode activated successfully!")
            print("Airtel mode activated with valid password")
        else:
            airtel_authenticated = False
            print("BSNL mode selected - Airtel authentication reset")

        # Clear UI when switching modes
        clear_ui_data()

        # Show mode change message in output
        mode_name = "Airtel" if selected_mode == 2 else "BSNL"
        output_queue.put(f"\n--- Switched to {mode_name} Mode ---\n")

    def clear_ui_data():
        global stopwatch_running, stop_event, airtel_authenticated
        """Clear all UI data and reset for next test"""
        stop_event.clear()
        if qr_code:
            qr_code.delete(0, tk.END)

        # Clear output text
        if output_text:
            output_text.delete("1.0", tk.END)

        if result_var:
            result_var.set("")
        if reason_var:
            reason_var.set("")

        # Reset progress
        if progress_var:
            progress_var.set(0)
        if progress_label_var:
            progress_label_var.set("Extraction stopped")
        reset_colors()

        if stopwatch_running:
            stopwatch.stop()
            stopwatch_running = False
        stopwatch_var.set("00:00:00")

        # Reset button text to "START"
        if start_button:
            start_button.config(text="START")
        try:
            from test_04 import ser1
            if 'ser1' in globals() and ser1 and ser1.is_open:
                ser1.close()
                print("Serial port closed")
        except:
            pass
        print("UI data cleared - ready for next test")

    def load_config(file_path="API&Pwd.txt"):
        config = {}
        try:
            with open(file_path, "r") as file:
                for line in file:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        config[key] = value
        except FileNotFoundError:
            print(f"Config file {file_path} not found. Using defaults.")
            config = {"BASE_URL": "http://default.url", "AIRTEL_PASSWORD": "default"}
        return config

    def start_button_clicked():
        global stop_event, stopwatch_running, airtel_authenticated, extraction_thread
        if stopwatch_running or (start_button and start_button.cget("text") == "STOP"):
            stop_event.set()
            stopwatch_running = False
            if stopwatch:
                stopwatch.stop()
            try:
                from test_04 import ser1
                if 'ser1' in globals() and ser1 and ser1.is_open:
                    ser1.close()
                    print("Serial port closed due to stop")
            except:
                pass

            start_button.config(text="START")
            reset_colors()
            stopwatch_var.set("00:00:00")
            output_queue.put("\n--- STOPPED BY USER ---\n")
            root.after(1000, lambda: check_thread_and_clear(extraction_thread))
            return

        stop_event.clear()
        if not validate_inputs(com_port_var, baudrate_var, operator_name_entry, qa_name_entry, qr_code):
            return

        clear_result_display()
        reset_colors()
        selected_device = com_port_var.get().split(" - ")[0]
        baudrate = baudrate_var.get()
        operator_name = operator_name_entry.get()
        qa_name = qa_name_entry.get()
        qr_code_value = qr_code.get()
        print("QR Code:", qr_code_value)
        config = load_config()
        BASE_URL = config["BASE_URL"]
        Aepl_URL = config["Aepl_URL"]

        SUCCESS_COLOR = "green"
        FAIL_COLOR = "red"

        # if not qr_code_value:
        #     messagebox.showerror("QR Code", "Please Scan QR code then Proceed")
        #     return

        # # Uncomment this section if you want API validation before starting
        # try:
        #     url = f"{BASE_URL}/{qr_code_value}"
        #     response = requests.get(url, timeout=5)
        #     data = response.json()
        #     if not data.get("status"):
        #         api_message = data.get("message", "Unknown error")

        #         success, serial_number = combine_and_save_QR(
        #             operator_name=operator_name,
        #             qa_name=qa_name,
        #             qr_code_value=qr_code_value,
        #             api_response_data=data,
        #             result_status="FAIL",
        #             failure_reason=api_message
        #         )
        #         if success:
        #             result_var.set("FAIL")
        #             reason_var.set(api_message)
        #             result_display_label.configure(foreground="red")
        #             qr_code.config(bg=FAIL_COLOR, fg="white")
        #             root.after(5000, lambda: [
        #                 qr_code.config(bg="white", fg="black"),
        #                 qr_code.delete(0, tk.END)
        #             ])
        #             messagebox.showerror("Status", f"{api_message}")

        #             # Update fail count and total count
        #             try:
        #                 current_fail = int(fail_count_var.get().split(": ")[1])
        #             except Exception:
        #                 current_fail = 0
        #             fail_count_var.set(f"Fail Count: {current_fail + 1}")
        #             update_total_count()
        #             start_button.config(text="START")
        #             reset_colors()
        #             stopwatch_var.set("00:00:00")
        #             output_queue.put("\n--- STOPPED BY USER ---\n")
        #             root.after(1000, lambda: check_thread_and_clear(extraction_thread))
        #             # root.after(0, lambda: reset_ui_for_next_test())

        #         else:
        #             print("Failed to save screwing station result to Excel")
        #         return
        #     qr_code.config(bg=SUCCESS_COLOR, fg="white")
        #     # root.after(0, lambda: reset_ui_for_next_test())
        # except Exception as e:
        #     error_message = f"Failed to connect to screwing station: {e}"
        #     messagebox.showerror("Connection Error", error_message)

        #     success, serial_number = combine_and_save_QR(
        #         operator_name=operator_name,
        #         qa_name=qa_name,
        #         qr_code_value=qr_code_value,
        #         api_response_data={"error": str(e)},
        #         result_status="ERROR",
        #         failure_reason=error_message
        #     )
        #     if success:
        #         result_var.set("ERROR")
        #         reason_var.set(error_message)
        #         result_display_label.configure(foreground="red")
        #         current_fail_count = int(fail_count_var.get().split(": ")[1])
        #         fail_count_var.set(f"Fail Count: {current_fail_count + 1}")
        #         update_total_count()
        #         start_button.config(text="START")
        #         reset_colors()
        #         stopwatch_var.set("00:00:00")
        #         output_queue.put("\n--- STOPPED BY USER ---\n")
        #         root.after(1000, lambda: check_thread_and_clear(extraction_thread))
        #     return

        # if not selected_device or not operator_name or not qa_name or not qr_code_value:
        #     messagebox.showerror("Error", "Please fill all fields")
        #     return

        if baudrate != '115200':
            messagebox.showerror("Error", "Please select the correct baudrate (115200)")
            return

        if not operator_name.isalpha() or not qa_name.isalpha():
            messagebox.showerror("Error",
                                 "Please input correct names (only alphabetic characters are allowed).")
            return

        # Password check for Airtel mode
        testing_stage = radio_value.get()
        if testing_stage == 2:  # Airtel mode
            if not airtel_authenticated:
                entered_password = simpledialog.askstring(
                    "Password Required",
                    "Enter Airtel activation password:",
                    show="*",
                    parent=root
                )

                if entered_password is None:
                    messagebox.showwarning("Cancelled", "Airtel activation cancelled.")
                    return

                AIRTEL_PASSWORD = config.get("AIRTEL_PASSWORD", "")
                if entered_password != AIRTEL_PASSWORD:
                    messagebox.showerror("Access Denied", "Incorrect password!")
                    return

                airtel_authenticated = True
                print("Airtel mode activated with valid password")
            else:
                print("Airtel mode already authenticated in this session")
        else:  # BSNL mode
            airtel_authenticated = False

        # Start the process
        stop_event.clear()
        stopwatch_running = True
        start_button.config(text="STOP")

        def execute_combine_and_save():
            """Main extraction function with improved progress bar"""
            try:
                # Start the stopwatch
                root.after(0, lambda: stopwatch.start())
                root.after(0, lambda: progress_label_var.set("Extraction started"))
                root.after(0, lambda: progress_var.set(0))

                # Flag to track completion
                extraction_complete = False

                def animate_progress():
                    """Animate progress bar smoothly during extraction"""
                    nonlocal extraction_complete
                    current_progress = 0
                    max_animated_progress = 90  # Stop at 90% until actual completion

                    while not extraction_complete and not stop_event.is_set():
                        if current_progress < max_animated_progress:
                            # Increment by 0.5% every 100ms for smooth animation
                            current_progress += 0.2
                            if current_progress > max_animated_progress:
                                current_progress = max_animated_progress
                            root.after(0, lambda p=current_progress: progress_var.set(p))
                        time.sleep(0.1)

                    # Set to 100% only if completed successfully
                    if not stop_event.is_set() and extraction_complete:
                        root.after(0, lambda: progress_var.set(100))

                # Start progress animation in separate thread
                progress_thread = threading.Thread(target=animate_progress, daemon=True)
                progress_thread.start()

                # Initialize variables
                result = "STOPPED"
                serial_number = 0
                condition_met_DO1 = "False"
                condition_met_DO2 = "False"
                imei = ''
                iccid = ''

                try:
                    if testing_stage == 1:
                        print("BSNL mode activated", testing_stage)
                        result, serial_number, condition_met_DO1, condition_met_DO2, imei, iccid = combine_and_save_dataframes(
                            selected_device, stop_event, operator_name, qa_name, qr_code_value
                        )
                    else:
                        print("Airtel mode activated", testing_stage)
                        result, serial_number, condition_met_DO1, condition_met_DO2, imei, iccid = combine_and_save_dataframes1(
                            selected_device, stop_event, operator_name, qa_name, qr_code_value
                        )
                except Exception as func_error:
                    print(f"Error calling extraction function: {func_error}")
                    import traceback
                    traceback.print_exc()
                    if not stop_event.is_set():
                        result = "ERROR"
                # Mark extraction as complete
                extraction_complete = True
                # Small delay to let progress animation reach 90%
                time.sleep(0.2)
                # Schedule QR code reset after 2 seconds
                root.after(2000, lambda: [
                    qr_code.config(bg="white", fg="black") if qr_code else None,
                    qr_code.delete(0, tk.END) if qr_code else None
                ])

                # Handle different result types
                if result == "STOPPED" or stop_event.is_set():
                    root.after(0, lambda: progress_label_var.set("Extraction stopped by user"))
                    root.after(0, lambda: reset_ui_for_next_test())
                else:
                    # Success case (PASS or FAIL) - Show results and stop stopwatch
                    root.after(0, lambda: call_aepl_api(operator_name, qa_name, qr_code_value, imei, iccid, result))
                    root.after(100, lambda: update_DO_result(condition_met_DO1, condition_met_DO2))
                    root.after(0, lambda: progress_label_var.set("Extraction completed"))
                    # root.after(0, lambda: call_aepl_api(qr_code_value, imei, iccid, result))

                    # Ensure progress bar is 100%
                    root.after(0, lambda: progress_var.set(100))

                    # STOP THE STOPWATCH HERE
                    root.after(0, lambda: stopwatch.stop())
                    root.after(0, lambda: setattr(sys.modules[__name__], 'stopwatch_running', False))

                    print("Test completed - Press STOP to clear and start next test")

            except Exception as e:
                if not stop_event.is_set():
                    root.after(0, lambda: output_queue.put(f"An unexpected error occurred: {e}\n"))

                root.after(0, lambda: progress_var.set(0))
                root.after(0, lambda: progress_label_var.set("Extraction stopped"))

                # Stop the stopwatch on exception
                root.after(0, lambda: stopwatch.stop())
                root.after(0, lambda: setattr(sys.modules[__name__], 'stopwatch_running', False))
                root.after(0, lambda: reset_ui_for_next_test())

            finally:
                if stop_event.is_set():
                    root.after(0, lambda: start_button.config(text="START"))

        # Store the thread reference and start it
        extraction_thread = threading.Thread(target=execute_combine_and_save, daemon=True)
        extraction_thread.start()

    def check_thread_and_clear(thread):
        """Check if thread has finished and then clear UI"""
        if thread and thread.is_alive():
            # Thread still running, check again in 500ms
            root.after(500, lambda: check_thread_and_clear(thread))
        else:
            # Thread finished, now clear UI
            clear_ui_data()
            output_queue.put("\n--- Ready for next test ---\n")
            root.after(100, qr_code.focus_set)

    def update_date_time():
        current_date = datetime.now().strftime('%d-%m-%Y')
        date_var.set(current_date)

        current_time = datetime.now().strftime('%H:%M:%S')
        time_var.set(current_time)

        root.after(1000, update_date_time)

    def clear_result_display():
        result_var.set("")
        reason_var.set("")
        output_text.delete("1.0", tk.END)
        # progress_var.set(0)
        progress_label_var.set("Extraction stopped")

    def call_aepl_api(operator_name, qa_name, qr_code_value, imei, iccid, result):
        print("sending this imei & iccid to server", imei, iccid)
        config = load_config()
        url = config["Aepl_URL"]
        api_url = f"{url}"

        # Add server connection check before proceeding
        if not check_server_connection(api_url):
            messagebox.showerror("Connection Error",
                                 "Cannot reach the server. Please check your network connection and server availability.")
            return False, {"error": "Server unreachable", "details": "Connection check failed"}

        if result == "PASS":
            result_bool = True
            # Prepare the data payload
            payload = {
                "pcbCode": str(qr_code_value),
                "imei": str(imei),
                "iccid": str(iccid),
                "status": bool(result_bool)
            }

            # Make POST request
            response = requests.post(
                api_url,
                json=payload,
                timeout=20
            )

            # Check if request was successful
            if response.status_code == 200:
                print("--------------------------------------------")
                print(f"API call successful!")
                print("--------------------------------------------")
                response_data = response.json()
                print(f"Response: {response_data}")
                print("--------------------------------------------")

                if response_data.get('status') == True:
                    final_result = "PASS"
                    # # Save to Excel with empty failure reason for PASS
                    # success = combine_and_save_QR1(failure_reason="")
                    # if success:
                    #     print("Excel updated successfully for PASS")
                else:
                    final_result = "FAIL"
                    # Check status in response
                    if response_data.get('status') == False:
                        # Get error message from response
                        error_message = response_data.get('message', 'No message')

                        # Get additional data if available
                        data = response_data.get('data', {})

                        # Format complete error details
                        full_error = f"Status: False\n\nMessage: {error_message}\n"

                        # Add data details if they exist
                        if data:
                            full_error += f"\nDetails:"
                            for key, value in data.items():
                                full_error += f"\n  • {key}: {value}"

                        messagebox.showwarning("API Warning", full_error)

                        # Save to Excel with failure reason for FAIL
                        success = combine_and_save_QR1(failure_reason=full_error)
                        if success:
                            print(f"Excel updated with failure reason: {full_error[:100]}...")

                update_result_display(final_result)
                return final_result, response_data
            else:
                # Handle non-200 response
                error_msg = f"API returned status code: {response.status_code}"
                messagebox.showerror("API Error", error_msg)
                success = combine_and_save_QR1(failure_reason=error_msg)
                update_result_display("FAIL")
                return "FAIL", {"error": error_msg}

        else:  # result is not "PASS"
            result_bool = False
            # Prepare the data payload
            payload = {
                "pcbCode": str(qr_code_value),
                "imei": str(imei),
                "iccid": str(iccid),
                "status": bool(result_bool)
            }

            # Make POST request
            response = requests.post(
                api_url,
                json=payload,
                timeout=20
            )

            # Check if request was successful
            if response.status_code == 200:
                final_result = "FAIL"
                print("--------------------------------------------")
                print(f"API call successful!")
                print("--------------------------------------------")
                response_data = response.json()
                print(f"Response: {response_data}")
                print("--------------------------------------------")
                update_result_display(final_result)
                return final_result, response_data
            else:
                error_msg = f"API returned status code: {response.status_code}"
                success = combine_and_save_QR1(failure_reason=error_msg)
                update_result_display("FAIL")
                # return "FAIL", {"error": error_msg}



    # def call_aepl_api(operator_name, qa_name, qr_code_value, imei, iccid, result):
    #     print("sending this imei & iccid to server", imei, iccid)
    #     """Post data to AEPL server API"""
    #     # print("AEPL server parameters:", qr_code_value, imei, iccid, result)
    #     config = load_config()
    #     url = config["Aepl_URL"]
    #     api_url = f"{url}"
    #     if result == "PASS":
    #         result = True
    #         # Prepare the data payload
    #         payload = {
    #             "pcbCode": str(qr_code_value),
    #             "imei": str(imei),
    #             "iccid": str(iccid),
    #             "status": bool(result)
    #         }
    #
    #         # Make POST request
    #         response = requests.post(
    #             api_url,
    #             json=payload,  # Automatically converts to JSON
    #             timeout=20  # 20 second timeout
    #         )
    #
    #         # Check if request was successful
    #         if response.status_code == 200:
    #             print("--------------------------------------------")
    #             print(f"API call successful!")
    #             print("--------------------------------------------")
    #             response_data = response.json()
    #             print(f"Response: {response_data}")
    #             print("--------------------------------------------")
    #
    #             if response_data.get('status') == True:
    #                 final_result = "PASS"
    #             else:
    #                 final_result = "FAIL"
    #                 server_result = "PASS"
    #                 # Check status in response
    #                 if response_data.get('status') == False:
    #                     # Get error message from response
    #                     error_message = response_data.get('message', 'No message')
    #
    #                     # Get additional data if available
    #                     data = response_data.get('data', {})
    #
    #                     # Format complete error details
    #                     full_error = f"Status: False\n\nMessage: {error_message}\n"
    #
    #                     # Add data details if they exist
    #                     if data:
    #                         full_error += f"\nDetails:"
    #                         for key, value in data.items():
    #                             full_error += f"\n  • {key}: {value}"
    #
    #                     messagebox.showwarning("API Warning", full_error)
    #                     # Save to Excel with failure reason
    #                     success, serial_number = combine_and_save_QR1(
    #                         failure_reason=full_error  # This will be empty for PASS
    #                     )
    #
    #             update_result_display(final_result)
    #             return final_result, response_data
    #     else:
    #         result = False
    #         # Prepare the data payload
    #         payload = {
    #             "pcbCode": str(qr_code_value),
    #             "imei": str(imei),
    #             "iccid": str(iccid),
    #             "status": bool(result)
    #         }
    #
    #         # Make POST request
    #         response = requests.post(
    #             api_url,
    #             json=payload,  # Automatically converts to JSON
    #             timeout=20  # 20 second timeout
    #         )
    #
    #         # Check if request was successful
    #         if response.status_code == 200:
    #             final_result = "False"
    #             print("--------------------------------------------")
    #             print(f"API call successful!")
    #             print("--------------------------------------------")
    #             response_data = response.json()
    #             print(f"Response: {response_data}")
    #             print("--------------------------------------------")
    #
    #             update_result_display(final_result)
    #
    #     # Add server connection check before proceeding
    #     if not check_server_connection(api_url):
    #         messagebox.showerror("Connection Error",
    #                              "Cannot reach the server. Please check your network connection and server availability.")
    #         return False, {"error": "Server unreachable", "details": "Connection check failed"}



    # Add this helper function outside or inside your class
    def check_server_connection(url, timeout=10):
        """Check if server is reachable before making the actual request"""
        try:
            # Try a HEAD request first (lighter than GET)
            response = requests.head(url, timeout=timeout, allow_redirects=True)
            # Server is reachable if status code is not 5xx
            return response.status_code < 500
        except requests.exceptions.RequestException:
            try:
                # Fallback to GET if HEAD is not allowed (with stream to avoid downloading)
                response = requests.get(url, timeout=timeout, stream=True)
                response.close()  # Close immediately
                return response.status_code < 500
            except requests.exceptions.RequestException:
                return False

    def update_result_display(result):
        print("Updating result display with:", result)
        result_var.set(result)
        reasons = []

        if result == "ERROR":
            result_display_label.configure(foreground="red")
            try:
                current_fail_text = fail_count_var.get()
                current_fail = int(current_fail_text.split(": ")[1])
                fail_count_var.set(f"Fail Count: {current_fail + 1}")
            except:
                fail_count_var.set("Fail Count: 1")

            update_total_count()

        if result == "FAIL":
            if reasons:
                reason_var.set(", ".join(reasons))
            else:
                reason_var.set("Test Failed")

            result_display_label.configure(foreground="red")
            try:
                current_fail_text = fail_count_var.get()
                current_fail = int(current_fail_text.split(": ")[1])
                fail_count_var.set(f"Fail Count: {current_fail + 1}")
            except:
                fail_count_var.set("Fail Count: 1")

            update_total_count()

        else:  # PASS result
            result_display_label.configure(foreground="green")
            reason_var.set("")
            try:
                current_pass_text = pass_count_var.get()
                current_pass = int(current_pass_text.split(": ")[1])
                pass_count_var.set(f"Pass Count: {current_pass + 1}")
            except:
                pass_count_var.set("Pass Count: 1")

            # Update total count
            update_total_count()

    def update_DO_result(condition_met_DO1, condition_met_DO2):
        print("condition DO1*:", condition_met_DO1)
        print("condition DO2*:", condition_met_DO2)

        if condition_met_DO1 == "True":
            print("Setting DO1 to green")
            canvas.itemconfig(circle1, fill="green")
        else:
            print("Setting DO1 to red")
            canvas.itemconfig(circle1, fill="red")

        if condition_met_DO2 == "True":
            print("Setting DO2 to green")
            canvas.itemconfig(circle2, fill="green")
        else:
            print("Setting DO2 to red")
            canvas.itemconfig(circle2, fill="red")
        canvas.update()

    def on_closing():
        """Handle application closing"""
        global airtel_authenticated, stopwatch_running, stop_event
        airtel_authenticated = False  # Reset authentication when app closes

        if stopwatch_running:
            stop_event.set()

        # # Initialize counts
        # total_count_label.config(text="0")
        # pass_count_var.set("Pass Count: 0")
        # fail_count_var.set("Fail Count: 0")

        # Close serial port
        try:
            from test_04 import ser1
            if 'ser1' in globals() and ser1 and ser1.is_open:
                ser1.close()
        except:
            pass

        root.destroy()

    # Create additional Tkinter variables that need root window
    date_var = tk.StringVar(root, value=datetime.now().strftime('%d-%m-%Y'))
    time_var = tk.StringVar(root, value=datetime.now().strftime('%H:%M:%S'))
    result_var = tk.StringVar(value="")
    reason_var = tk.StringVar()
    progress_var = tk.DoubleVar()
    progress_label_var = tk.StringVar()

    # GUI Layout
    blue_white = '#ecf0f1'
    left_space = int(1 * 38)
    top_space = int(1 * 38)

    # QR Code
    qr_label = tk.Label(root, text="Scan QR:", font=('Helvetica', 12, 'bold'))
    qr_label.place(x=5, y=root.winfo_screenheight() - 520, anchor='sw')

    qr_code = tk.Entry(root, width=44, font=('Helvetica', 10), justify='left')
    qr_code.place(x=85, y=root.winfo_screenheight() - 525, anchor='sw')

    # COM Port Selection
    initial_devices = get_connected_devices()
    com_port_label = tk.Label(root, text="Select COM Port and Baudrate:", font=('Helvetica', 13, 'bold'))
    com_port_label.place(x=20, y=root.winfo_screenheight() - 440, anchor='sw')

    com_port_dropdown = ttk.Combobox(root, textvariable=com_port_var,
                                     values=[f"{device[0]} - {device[1]}" for device in initial_devices],
                                     state='readonly', width=50)
    com_port_dropdown.place(x=20, y=root.winfo_screenheight() - 390, anchor='sw')

    baudrate_options = ['115200', '9600', '19200', '38400', '57600']
    baudrate_dropdown = ttk.Combobox(root, textvariable=baudrate_var, values=baudrate_options, state='readonly',
                                     width=30)
    baudrate_dropdown.place(x=20, y=root.winfo_screenheight() - 340, anchor='sw')
    baudrate_var.set(baudrate_options[0])  # Set default baudrate

    # Update Button
    update_button = tk.Button(root, text="Update List", command=update_dropdown)
    update_button.place(x=95, y=root.winfo_screenheight() - 250, anchor='sw')

    # Mode Selection
    radio_value = tk.IntVar()
    radio_value.set(1)  # Set default to BSNL

    bsnl_radio = tk.Radiobutton(
        root,
        text="BSNL Mode",
        variable=radio_value,
        value=1,
        font=('Arial', 10),
        command=on_operator_mode_change
    )
    bsnl_radio.place(x=100, y=220)

    airtel_radio = tk.Radiobutton(
        root,
        text="Airtel Mode",
        variable=radio_value,
        value=2,
        font=('Arial', 10),
        command=on_operator_mode_change
    )
    airtel_radio.place(x=240, y=220)

    # Connect Button
    connect_button = tk.Button(root, text="CONNECT", command=connect_button_clicked)
    connect_button.place(x=95, y=root.winfo_screenheight() - 200, anchor='sw')

    # Start/Stop Button
    start_button = ttk.Button(root, text="START", command=start_button_clicked, style='Start.TButton')
    start_button.place(x=15, y=7 * 38 + 300, anchor='nw')
    start_button.configure(width=18)
    start_button.configure(padding=(5, 10))
    start_button.focus_set()
    # Use <Return> for Enter key, not <space>
    root.bind('<Return>', lambda event: start_button_clicked())

    # Style
    root.style = ttk.Style()
    root.style.configure("Start.TButton", font=('Helvetica', 16, 'bold'))

    # Output Text Area
    serial_data_container = ttk.Frame(root, padding="10")
    serial_data_container.place(x=860, y=top_space + 3.2 * 38 + 20, anchor='nw')

    output_text = scrolledtext.ScrolledText(serial_data_container, wrap=tk.WORD, width=48, height=20)
    output_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    # Redirect stdout
    sys.stdout = RedirectText(output_queue, output_text)

    # User Details Container
    user_details_container = ttk.LabelFrame(root, text="User Details")
    user_details_container.place(x=left_space, y=top_space, anchor='nw')

    user_details_label = tk.Label(user_details_container, text="User Details", font=('Helvetica', 12), anchor='w',
                                  padx=5)
    user_details_label.grid(row=0, column=0, sticky='w', pady=5)

    operator_name_label = tk.Label(user_details_container, text="Operator Name", font=('Helvetica', 10), anchor='w',
                                   padx=5)
    operator_name_label.grid(row=1, column=0, sticky='w', pady=2)

    operator_name_entry = tk.Entry(user_details_container, width=12, font=('Helvetica', 10), justify='center')
    operator_name_entry.grid(row=1, column=1, pady=2, padx=2)

    qa_name_label = tk.Label(user_details_container, text="QA Name", font=('Helvetica', 10), anchor='w', padx=5)
    qa_name_label.grid(row=2, column=0, sticky='w', pady=2)

    qa_name_entry = tk.Entry(user_details_container, width=12, font=('Helvetica', 10), justify='center')
    qa_name_entry.grid(row=2, column=1, pady=2, padx=2)

    # Project Details Container
    project_details_container = ttk.LabelFrame(root, text="FINAL TESTING")
    project_details_container.place(x=9 * 38 + 2 * left_space, y=top_space, anchor='nw')

    final_testing_label = tk.Label(project_details_container, text="TCU - 4G", font=('Helvetica', 30, 'bold'),
                                   anchor='n', pady=5)
    final_testing_label.pack()

    project_name_label = tk.Label(project_details_container, text="ADVANCED TELEMATICS CONTROL UNIT",
                                  font=('Helvetica', 10), anchor='w', padx=5)
    project_name_label.pack(anchor='w', pady=2)

    # Date and Time Container
    date_time_container = ttk.LabelFrame(root, text="Date and Time")
    date_time_container.place(x=2 * 8 * 42 + 3 * left_space, y=top_space, anchor='nw')

    date_label = tk.Label(date_time_container, text="DATE", font=('Helvetica', 10), anchor='w', padx=5)
    date_label.grid(row=0, column=0, sticky='w', pady=2)

    date_entry = tk.Entry(date_time_container, textvariable=date_var, width=12, font=('Helvetica', 10),
                          justify='center', state='readonly')
    date_entry.grid(row=0, column=1, pady=2, padx=2)

    time_label = tk.Label(date_time_container, text="TIME", font=('Helvetica', 10), anchor='w', padx=5)
    time_label.grid(row=1, column=0, sticky='w', pady=2)

    time_entry = tk.Entry(date_time_container, textvariable=time_var, width=12, font=('Helvetica', 10),
                          justify='center', state='readonly')
    time_entry.grid(row=1, column=1, pady=2, padx=2)

    update_date_time()

    stopwatch_label = tk.Label(date_time_container, text="Stopwatch", font=('Helvetica', 10), anchor='w', padx=5)
    stopwatch_label.grid(row=2, column=0, sticky='w', pady=2)

    stopwatch_display = tk.Label(date_time_container, textvariable=stopwatch_var, font=('Helvetica', 10), anchor='w',
                                 padx=5)
    stopwatch_display.grid(row=2, column=1, sticky='w', pady=2)

    stopwatch = Stopwatch(stopwatch_var)

    # Logo Container
    logo_container = ttk.LabelFrame(root, text="ACCOLADE ELECTRONICS PRIVATE LIMITED")
    logo_container.place(x=2.6 * 9 * 36 + 4 * left_space, y=top_space, anchor='nw',
                         width=260,height=130)

    logo_label = tk.Label(logo_container, bd=0)
    logo_label.grid(row=0, column=0, sticky='e', pady=5)
    # logo_label.place(x=50, y=50)

    try:
        image = Image.open(image_file_path)
        # image = tk.PhotoImage(file=image_file_path)
        image = image.resize((220, 100))
        image = ImageTk.PhotoImage(image) 

        logo_label.config(image=image)
        logo_label.image = image
        logo_label.place(x=20, y=5)
    except tk.TclError as e:
        print(f"Error loading image: {e}. Path used: {image_file_path}")

    # Line Canvas
    line_canvas = tk.Canvas(root, height=2, width=root.winfo_screenwidth(), bg=blue_white, highlightthickness=0)
    line_canvas.create_line(0, 0, root.winfo_screenwidth(), 0, fill='black')
    line_canvas.place(x=0, y=top_space + 3 * 38 + 20, anchor='nw')

    # Progress Frame
    progress_frame = ttk.LabelFrame(root, text="Progress", padding="10")
    progress_frame.place(x=860, y=top_space + 13 * 38 + 30, anchor='nw', width=400, height=80)

    progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", length=200, mode="determinate",
                                   variable=progress_var)
    progress_bar.grid(row=0, column=0, padx=10, pady=10)

    progress_label = ttk.Label(progress_frame, textvariable=progress_label_var, font=('Helvetica', 10))
    progress_label.grid(row=0, column=1, padx=10, pady=10)

    # Total Count Container (updated)
    total_count_container = ttk.LabelFrame(root, text="Total Count")
    total_count_container.place(x=400, y=top_space + 10 * 38 + 40, anchor='nw')

    total_count_label = tk.Label(total_count_container, textvariable=total_count_var, font=('Helvetica', 12))
    total_count_label.grid(row=0, column=0, sticky='w', pady=5, padx=10)

    pass_count_label = tk.Label(total_count_container, textvariable=pass_count_var, font=('Helvetica', 12))
    pass_count_label.grid(row=1, column=0, sticky='w', pady=5, padx=10)

    fail_count_label = tk.Label(total_count_container, textvariable=fail_count_var, font=('Helvetica', 12))
    fail_count_label.grid(row=2, column=0, sticky='w', pady=5, padx=10)

    # Result Container
    result_container = ttk.LabelFrame(root, text="Result", padding="10")
    result_container.place(x=400, y=top_space + 3.2 * 38 + 40, anchor='nw', width=400, height=200)

    result_label = ttk.Label(result_container, text="Result:", font=('Helvetica', 12))
    result_label.grid(row=0, column=0, sticky='w', pady=5, padx=10)

    result_display_label = ttk.Label(result_container, textvariable=result_var, font=('Helvetica', 32, 'bold'))
    result_display_label.grid(row=0, column=1, sticky='w', pady=5)

    reason_display_label = ttk.Label(result_container, textvariable=reason_var, font=('Helvetica', 12), wraplength=380)
    reason_display_label.grid(row=1, column=0, columnspan=2, pady=5, padx=10)

    # Digital Status Container
    status_container = ttk.LabelFrame(root, text="Digital Status", width=100, height=10)
    status_container.place(x=550, y=450)

    canvas = tk.Canvas(status_container, width=210, height=110)
    canvas.pack(padx=20, pady=20)

    # Draw two circles representing digital status
    circle1 = canvas.create_oval(30, 30, 100, 100, fill="red")
    circle2 = canvas.create_oval(120, 30, 190, 100, fill="red")

    # Add names inside the circles
    canvas.create_text(65, 65, text="DO1", font=("Arial", 15))
    canvas.create_text(160, 65, text="DO2", font=("Arial", 15))

    # Set up closing handler
    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Start the update_output function
    root.after(100, update_output)
    root.mainloop()


# Only call create_widgets() once
if __name__ == "__main__":
    create_widgets()