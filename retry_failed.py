#!/usr/bin/env python3
import os
import re
import json

def parse_command(cmd):
    out_match = re.search(r'> (./tests/results/[^\s]+.out)', cmd)
    err_match = re.search(r'2> (./tests/results/[^\s]+.err)', cmd)
    json_match = re.search(r'echo \'.*\' > (./tests/results/[^\s]+.json)', cmd)
    
    pddl_matches = re.findall(r'./instances/FD-IPC-opt-strips/[^\s]+/[^\s]+.pddl', cmd)
    domain, instance = "?", "?"
    if len(pddl_matches) >= 2:
        parts = pddl_matches[1].split('/')
        domain = parts[-2]
        instance = parts[-1].replace('.pddl', '')
        
    out_path = out_match.group(1) if out_match else None
    err_path = err_match.group(1) if err_match else None
    json_path = json_match.group(1) if json_match else None
    
    return {
        'out_path': out_path,
        'err_path': err_path,
        'json_path': json_path,
        'domain': domain,
        'instance': instance,
        'command': cmd
    }

def main():
    job_files = ['jobs_1.txt', 'jobs_2.txt', 'jobs_3.txt']
    runs = []
    
    for jfile in job_files:
        if not os.path.exists(jfile):
            continue
        with open(jfile) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    runs.append(parse_command(line))
                    
    retry_runs = []
    solved_count = 0
    planner_timeout_count = 0
    oom_count = 0
    crashed_count = 0
    slurm_timeout_count = 0
    missing_count = 0
    
    for run in runs:
        out_path = run['out_path']
        err_path = run['err_path']
        json_path = run['json_path']
        
        # Missing Check
        if not out_path or not os.path.exists(out_path):
            missing_count += 1
            retry_runs.append(run)
            continue
            
        out_content = ""
        with open(out_path, 'r', errors='ignore') as f:
            out_content = f.read()
            
        err_content = ""
        if err_path and os.path.exists(err_path):
            with open(err_path, 'r', errors='ignore') as f:
                err_content = f.read()
                
        # 1. Solved Check
        if "Solution found" in out_content or "Insolution found" in out_content:
            solved_count += 1
            continue
            
        # 2. Out of Memory Check
        if "Memory limit exceeded" in out_content or "std::bad_alloc" in out_content or "Out of memory" in out_content or "std::bad_alloc" in err_content:
            oom_count += 1
            continue
            
        # 3. Planner Timeout Check (skip retrying)
        if "Search time limit exceeded" in out_content or "Time limit reached" in out_content:
            planner_timeout_count += 1
            continue
            
        # 4. SLURM Timeout Check (retry)
        if "DUE TO TIME LIMIT" in err_content or "CANCELLED" in err_content:
            slurm_timeout_count += 1
            retry_runs.append(run)
            continue
            
        # Check if json was not written (meaning script was killed abruptly)
        if not json_path or not os.path.exists(json_path):
            if "Actual search time:" not in out_content and "Search time:" not in out_content:
                slurm_timeout_count += 1
            else:
                crashed_count += 1
            retry_runs.append(run)
            continue
            
        # Default: crashed or failed run (retry)
        crashed_count += 1
        retry_runs.append(run)
        
    print("\n--- RETRY ANALYSIS ---")
    print(f"Total Configs Checked: {len(runs)}")
    print(f"Solved:              {solved_count}")
    print(f"Planner Timeout:     {planner_timeout_count} (skipped)")
    print(f"Out of Memory (OOM): {oom_count} (skipped)")
    print(f"SLURM Timeout:       {slurm_timeout_count} (will retry)")
    print(f"Crashed/Failed:      {crashed_count} (will retry)")
    print(f"Missing (No log):    {missing_count} (will retry)")
    print(f"TOTAL TO RETRY:      {len(retry_runs)}")
    print("----------------------")
    
    # Write failed commands to failed_jobs.txt
    with open('failed_jobs.txt', 'w') as f:
        for run in retry_runs:
            f.write(run['command'] + '\n')
            
    print(f"Wrote {len(retry_runs)} commands to failed_jobs.txt")
    
    sbatch_content = f"""#!/bin/bash
#SBATCH --partition=main
#SBATCH --time=9:00:00
#SBATCH --job-name=pea_ida_retry
#SBATCH --output=logs/retry_%A_%a.out
#SBATCH --error=logs/retry_%A_%a.err
#SBATCH --mail-user=saarbu@post.bgu.ac.il
#SBATCH --mail-type=FAIL
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1

mkdir -p logs

module load anaconda
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate build_env

# Extract command for this task ID (1-indexed)
CMD=$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" failed_jobs.txt)

if [ -z "$CMD" ]; then
    echo "Error: No command found at line ${{SLURM_ARRAY_TASK_ID}} in failed_jobs.txt"
    exit 1
fi

echo "Task ID: ${{SLURM_ARRAY_TASK_ID}}"
echo "Running command: ${{CMD}}"
echo "----------------------------------------"

eval "$CMD"
"""

    with open('run_failed.sbatch', 'w') as f:
        f.write(sbatch_content)
        
    print(f"Generated run_failed.sbatch")
    print(f"To submit the retry job array:")
    print(f"  sbatch --array=1-{len(retry_runs)} run_failed.sbatch")

if __name__ == "__main__":
    main()
