#!/usr/bin/env python3
import os
import re
import json

def parse_command(cmd):
    # Regex to find output redirection and json path
    out_match = re.search(r'> (./tests/results/[^\s]+.out)', cmd)
    err_match = re.search(r'2> (./tests/results/[^\s]+.err)', cmd)
    json_match = re.search(r'echo \'.*\' > (./tests/results/[^\s]+.json)', cmd)
    
    # Extract domain and instance from command line
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
            print(f"Warning: {jfile} not found.")
            continue
        with open(jfile) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    runs.append(parse_command(line))
                    
    print(f"Loaded {len(runs)} runs from job files.")
    
    outcomes = {
        'solved': [],
        'planner_timeout': [],
        'slurm_timeout': [],
        'oom': [],
        'crashed': [],
        'missing': []
    }
    
    for run in runs:
        out_path = run['out_path']
        err_path = run['err_path']
        json_path = run['json_path']
        
        # Check if files exist
        if not out_path or not os.path.exists(out_path):
            outcomes['missing'].append(run)
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
            outcomes['solved'].append(run)
            continue
            
        # 2. Out of Memory Check
        if "Memory limit exceeded" in out_content or "std::bad_alloc" in out_content or "Out of memory" in out_content or "std::bad_alloc" in err_content:
            outcomes['oom'].append(run)
            continue
            
        # 3. Planner Timeout Check
        if "Search time limit exceeded" in out_content or "Time limit reached" in out_content:
            outcomes['planner_timeout'].append(run)
            continue
            
        # 4. SLURM Timeout Check
        if "DUE TO TIME LIMIT" in err_content or "CANCELLED" in err_content:
            outcomes['slurm_timeout'].append(run)
            continue
            
        # Check if json was not written (meaning script was killed abruptly)
        if not json_path or not os.path.exists(json_path):
            # If it ended abruptly without search statistics, it's likely a SLURM timeout
            if "Actual search time:" not in out_content and "Search time:" not in out_content:
                outcomes['slurm_timeout'].append(run)
            else:
                outcomes['crashed'].append(run)
            continue
            
        # 5. Crashed / Traceback Check
        if "Traceback" in out_content or "Traceback" in err_content or "Assertion" in out_content or "error" in out_content.lower() or "error" in err_content.lower():
            outcomes['crashed'].append(run)
        else:
            # Default to crashed / incomplete
            outcomes['crashed'].append(run)
            
    print("\n--- SUMMARY OF RESULTS ---")
    print(f"Total Configs Checked: {len(runs)}")
    print(f"Solved:              {len(outcomes['solved'])}")
    print(f"Planner Timeout:     {len(outcomes['planner_timeout'])}")
    print(f"SLURM Timeout:       {len(outcomes['slurm_timeout'])}")
    print(f"Out of Memory:       {len(outcomes['oom'])}")
    print(f"Crashed/Failed:      {len(outcomes['crashed'])}")
    print(f"Missing (No log):    {len(outcomes['missing'])}")
    print("--------------------------")
    
    # Write a detailed report
    os.makedirs('tests/analysis', exist_ok=True)
    report_path = 'tests/analysis/run_status_report.md'
    with open(report_path, 'w') as f:
        f.write("# SLURM Run Execution Status Report\n\n")
        f.write("## Overview\n")
        f.write(f"- **Total Configs**: {len(runs)}\n")
        f.write(f"- **Solved**: {len(outcomes['solved'])}\n")
        f.write(f"- **Planner Timeout**: {len(outcomes['planner_timeout'])}\n")
        f.write(f"- **SLURM Timeout**: {len(outcomes['slurm_timeout'])}\n")
        f.write(f"- **Out of Memory (OOM)**: {len(outcomes['oom'])}\n")
        f.write(f"- **Crashed/Failed**: {len(outcomes['crashed'])}\n")
        f.write(f"- **Missing (No Log)**: {len(outcomes['missing'])}\n\n")
        
        if outcomes['slurm_timeout']:
            f.write("## SLURM Timeouts (Aborted by Cluster)\n")
            f.write("The following runs exceeded the SLURM time limit (7 hours) and were cancelled by the queue:\n")
            for r in outcomes['slurm_timeout']:
                f.write(f"- `{r['domain']}` / `{r['instance']}`: [log]({r['out_path']})\n")
            f.write("\n")
            
        if outcomes['oom']:
            f.write("## Out of Memory (OOM)\n")
            for r in outcomes['oom']:
                f.write(f"- `{r['domain']}` / `{r['instance']}`: [log]({r['out_path']})\n")
            f.write("\n")
            
        if outcomes['crashed']:
            f.write("## Crashed or Failed runs\n")
            for r in outcomes['crashed']:
                f.write(f"- `{r['domain']}` / `{r['instance']}`: [log]({r['out_path']})\n")
            f.write("\n")
            
        if outcomes['missing']:
            f.write("## Missing (Not Executed / No Logs)\n")
            for r in outcomes['missing']:
                f.write(f"- `{r['domain']}` / `{r['instance']}`: `{r['out_path']}`\n")
            f.write("\n")
            
    print(f"\nDetailed report written to: {report_path}")

if __name__ == "__main__":
    main()
