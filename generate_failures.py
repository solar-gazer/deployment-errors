import os
import json
import time
import subprocess
import shutil
from automation.git_utils import commit_and_push
from automation.workflow_utils import wait_for_run
from config import TOTAL_RUNS, LOG_FOLDER, METADATA_FOLDER, FAILURE_TYPE

def load_scenarios():
    with open("deployment_errors.txt", "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def main():
    scenarios = load_scenarios()
    
    # Ensure nested raw directory exists
    raw_log_folder = f"{LOG_FOLDER}/raw"
    os.makedirs(raw_log_folder, exist_ok=True)
    os.makedirs(METADATA_FOLDER, exist_ok=True)
    
    print(f"Starting generation for {TOTAL_RUNS} runs of {FAILURE_TYPE}...")
    
    for i in range(1, TOTAL_RUNS + 1):
        scenario = scenarios[i % len(scenarios)]
        print(f"\n--- Run {i}/{TOTAL_RUNS}: {scenario} ---")
        
        # Modify a state file to force a Git commit
        state_file = f"state_{FAILURE_TYPE.lower()}.json"
        with open(state_file, "w") as f:
            json.dump({"run": i, "scenario": scenario}, f)
            
        sha = commit_and_push(f"Auto-trigger F4: {scenario} run {i}")
        if not sha:
            print("Commit failed, skipping...")
            continue
            
        print(f"Waiting for workflow on commit {sha[:7]}...")
        time.sleep(10) # Buffer for GitHub Actions to register
        
        # Grab the workflow result using your team's utils
        workflow_result = wait_for_run(sha)
        
        # Parse the output depending on how wait_for_run returns the data
        if isinstance(workflow_result, dict):
            workflow_id = workflow_result.get('databaseId') or workflow_result.get('id')
            status = workflow_result.get('conclusion', 'unknown')
        else:
            workflow_id = None
            status = str(workflow_result)
            
        print(f"Workflow finished with status: {status}")
        
        if workflow_id:
            print("Downloading logs...")
            temp_dir = f"temp_run_{i}"
            
            # Use GitHub CLI to download the logs
            subprocess.run(f"gh run download {workflow_id} -D {temp_dir}", shell=True, capture_output=True)
            
            # Find the text log and move it to our raw folder
            log_content = "Log download failed or GH CLI not authenticated."
            if os.path.exists(temp_dir):
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith('.txt'):
                            with open(os.path.join(root, file), 'r', encoding='utf-8') as file_in:
                                log_content = file_in.read()
                            break
                # Clean up the temp download folder
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            # Save the raw log
            with open(f"{raw_log_folder}/run_{i}.txt", "w", encoding='utf-8') as f:
                f.write(log_content)
            
            # Save the JSON metadata
            meta = {
                "run_id": i,
                "failure_type": FAILURE_TYPE,
                "scenario": scenario,
                "status": status,
                "commit_sha": sha
            }
            with open(f"{METADATA_FOLDER}/run_{i}.json", "w", encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
                
            print(f"✓ Saved raw log and metadata for run {i}")
        else:
            print("✗ Could not retrieve workflow ID. Skipping log download.")

if __name__ == "__main__":
    main()