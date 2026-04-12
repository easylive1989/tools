import re
import glob
from collections import defaultdict
import os

try:
    import numpy as np
except ImportError:
    print("Numpy is not installed. Please install it using 'pip install numpy' to get median and quartile statistics.")
    np = None

def analyze_project_days(directory_path):
    """
    Analyzes all markdown files in a directory to calculate the total days
    spent on each project and the overall average.

    The logic assumes:
    - Each non-indented line that doesn't start with a number is a project title.
    - Each line starting with 'N.' (e.g., '1.', '2.') under a title counts as one day.
    """
    if not os.path.isdir(directory_path):
        print(f"Error: Directory not found at '{directory_path}'")
        return

    # Use a defaultdict to easily increment counts
    project_days = defaultdict(int)

    # Find all markdown files in the specified directory
    file_paths = glob.glob(os.path.join(directory_path, '*.md'))

    if not file_paths:
        print(f"No markdown files found in '{directory_path}'")
        return

    # Regex to identify a line item that represents a day
    day_entry_regex = re.compile(r"^\s*\d+\.\s.*")
    
    # Regex to identify the main title of the file, which should be ignored
    main_title_regex = re.compile(r"^#\s\d+\sPlanning.*")

    current_project = None

    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines, "Created time" lines, and the main file title
                    if not line or "Created time:" in line or main_title_regex.match(line):
                        continue

                    # Check if the line is a day entry
                    if day_entry_regex.match(line):
                        if current_project:
                            project_days[current_project] += 1
                    else:
                        # This line is a new project title.
                        # Clean up prefixes for better grouping.
                        current_project = line.lstrip('V✓•- ').strip()
                        # Also strip '###' from section headers
                        if current_project.startswith('###'):
                            current_project = current_project.lstrip('#- ').strip()


        except Exception as e:
            print(f"Error reading or processing file {file_path}: {e}")

    # Sort projects by the number of days in descending order
    sorted_projects = sorted(project_days.items(), key=lambda item: item[1], reverse=True)

    # --- Output ---
    print("| {:<60} | {:<5} |".format("工作項目", "總天數"))
    print("| :{:-<60} | :{:-<5} |".format("", ""))
    for project, days in sorted_projects:
        print(f"| {project:<60} | {days:<5} |")
        
    # --- Statistics ---
    total_days_sum = sum(project_days.values())
    num_projects = len(project_days)
    
    print("\n" + "="*70)
    print(f"總項目數量: {num_projects}")
    print(f"總計天數: {total_days_sum}")

    if num_projects > 0:
        average_days = total_days_sum / num_projects
        print(f"每個項目的平均花費天數: {average_days:.2f} 天")
        
        if np:
            all_days = list(project_days.values())
            median_days = np.median(all_days)
            q1_days = np.percentile(all_days, 25)
            q3_days = np.percentile(all_days, 75)
            print(f"天數中位數 (Median): {median_days:.2f} 天")
            print(f"天數 Q1 (第 1 四分位數): {q1_days:.2f} 天")
            print(f"天數 Q3 (第 3 四分位數): {q3_days:.2f} 天")

    print("="*70)


if __name__ == "__main__":
    # Get the current working directory
    current_directory = os.getcwd()
    print(f"Analyzing files in: {current_directory}\n")
    analyze_project_days(current_directory)