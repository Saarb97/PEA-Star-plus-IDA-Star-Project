#!/usr/bin/env python3
import os
import copy
import json
import hashlib
from math import ceil, floor

heuristics = ['lmcut']

def get_pack(kwargs):
    common_kwargs = {
        'suite': kwargs['suite'],
        'cost_system': kwargs['cost_system'],
        'memory_limit': kwargs['memory_limit'],
        'time_limit': kwargs['time_limit'],
        'algorithm': kwargs['algorithm'],
        'open_limitness': kwargs['open_limitness'],
        'heuristic': kwargs['heuristic']
    }
    import operator
    return ','.join(list(map(operator.itemgetter(1), sorted(common_kwargs.items()))))

def generate_command(kwargs):
    # Stable hash for sas file name
    serialized = json.dumps(kwargs, sort_keys=True)
    hash_for_trash = hashlib.md5(serialized.encode()).hexdigest()
    pack = get_pack(kwargs)
    
    cmd_args = [
        "python3",
        "./fast-downward.py",
        "--validate",
        "--overall-memory-limit", kwargs['memory_limit'],
        "--translate-time-limit", kwargs['time_limit'],
        "--sas-file", f"./tests/trash/{hash_for_trash}.sas",
        "--plan-file", f"./tests/trash/{hash_for_trash}.plan",
        f"./instances/{kwargs['suite']}/{kwargs['domain']}/{kwargs['domain_pddl']}.pddl",
        f"./instances/{kwargs['suite']}/{kwargs['domain']}/{kwargs['instance_pddl']}.pddl",
        "--search", f"'{kwargs['algorithm_call']}({kwargs['heuristic_call']})'",
        "--time-limit", str(floor(1.2 * kwargs['time_limit_seconds']))
    ]
    
    if 'open_limit' in kwargs:
        cmd_args.extend(["--open-limit", kwargs['open_limit']])
    if 'is_using_partial_expansion' in kwargs:
        cmd_args.append("--partial-expansion")
    if 'second_phase_lower_bound' in kwargs:
        cmd_args.extend(["--second-phase-lower-bound", kwargs['second_phase_lower_bound']])
        
    cmd_str = " ".join(cmd_args)
    
    # Path setup
    out_dir = f"./tests/results/{pack}"
    filepath_json = f"{out_dir}/{kwargs['domain']}_{kwargs['instance_pddl']}.json"
    filepath_out = f"{out_dir}/{kwargs['domain']}_{kwargs['instance_pddl']}.out"
    filepath_err = f"{out_dir}/{kwargs['domain']}_{kwargs['instance_pddl']}.err"
    
    # Combined command string with execution, log redirection, json writing, and sas cleanup
    kwargs_escaped = json.dumps(kwargs).replace("'", "'\\''")
    full_cmd = (
        f"mkdir -p {out_dir} && "
        f"{cmd_str} > {filepath_out} 2> {filepath_err} ; "
        f"echo '{kwargs_escaped}' > {filepath_json} ; "
        f"rm -f ./tests/trash/{hash_for_trash}.sas ./tests/trash/{hash_for_trash}.plan*"
    )
    return full_cmd

def collect_configs():
    configs = []
    
    # Hybrid tests configurations
    common_kwargs = {
        'suite': 'FD-IPC-opt-strips',
        'cost_system': 'real-costs',
        'memory_limit': '2G',
        'time_limit': '360m',
    }
    
    algorithms = ['pe-edd-eh', 'edd-eh']
    open_limits = ['limited-90', 'limited-50', 'limited-10']
    
    for algorithm in algorithms:
        for open_limitness in open_limits:
            for heuristic in heuristics:
                kw = copy.deepcopy(common_kwargs)
                kw['algorithm'] = algorithm
                kw['open_limitness'] = open_limitness
                kw['heuristic'] = heuristic
                configs.append(kw)
                
    # Artificial hybrid tests configurations
    for open_limitness in ['limited-90-pebound-90', 'limited-50-pebound-50', 'limited-10-pebound-10']:
        for heuristic in heuristics:
            kw = copy.deepcopy(common_kwargs)
            kw['algorithm'] = 'edd-eh'
            kw['open_limitness'] = open_limitness
            kw['heuristic'] = heuristic
            configs.append(kw)
            
    return configs

def main():
    configs = collect_configs()
    all_commands = []
    
    # Ensure trash directory exists
    os.makedirs('./tests/trash', exist_ok=True)
    
    for common_kw in configs:
        pack = get_pack(common_kw)
        
        # Replicate filtering from tester.py
        for domain in sorted(os.listdir(f'./instances/{common_kw["suite"]}')):
            domain_path = f'./instances/{common_kw["suite"]}/{domain}'
            domain_pddls = list(sorted([x[:-5] for x in os.listdir(domain_path) if 'domain' in x and x.endswith('.pddl')]))
            instances_pddls = list(sorted([x[:-5] for x in os.listdir(domain_path) if not 'domain' in x and x.endswith('.pddl')]))
            
            for instance_index, instance_pddl in enumerate(instances_pddls):
                try:
                    kwargs = copy.deepcopy(common_kw)
                    kwargs['domain'] = domain
                    kwargs['instance_index'] = instance_index
                    kwargs['instance_pddl'] = instance_pddl
                    if len(domain_pddls) == 1:
                        kwargs['domain_pddl'] = domain_pddls[0]
                    else:
                        kwargs['domain_pddl'] = domain_pddls[instance_index]
                        
                    kwargs['time_limit_seconds'] = 360 * 60 # 360m
                    kwargs['memory_limit_bytes'] = 2 * 1000 * 1000 * 1000 # 2G
                    kwargs['heuristic_call'] = kwargs['heuristic'] + '()'
                    
                    if 'pe' in kwargs['algorithm']:
                        kwargs['is_using_partial_expansion'] = True
                    kwargs['algorithm_call'] = 'pea_ida'
                    
                    # Read corresponding baseline files to verify solving
                    astar_common_kwargs = copy.deepcopy(common_kw)
                    astar_common_kwargs['time_limit'] = '10m'
                    astar_common_kwargs['algorithm'] = 'edd-eh'
                    astar_common_kwargs['open_limitness'] = 'unlimited'
                    astar_pack = get_pack(astar_common_kwargs)
                    astar_out_path = f'./tests/baseline_results/{astar_pack}/{domain}_{instance_pddl}.out'
                    
                    if not os.path.exists(astar_out_path):
                        continue
                    astar_stdout = open(astar_out_path).read()
                    if not 'Solution found' in astar_stdout:
                        continue
                        
                    blind_astar_common_kwargs = copy.deepcopy(common_kw)
                    blind_astar_common_kwargs['time_limit'] = '10m'
                    blind_astar_common_kwargs['algorithm'] = 'edd-eh'
                    blind_astar_common_kwargs['open_limitness'] = 'unlimited'
                    blind_astar_common_kwargs['heuristic'] = 'blind'
                    blind_astar_pack = get_pack(blind_astar_common_kwargs)
                    blind_astar_out_path = f'./tests/baseline_results/{blind_astar_pack}/{domain}_{instance_pddl}.out'
                    
                    if not os.path.exists(blind_astar_out_path):
                        continue
                    blind_astar_stdout = open(blind_astar_out_path).read()
                    if 'Solution found' in blind_astar_stdout:
                        continue
                        
                    # Calculate open limit
                    value = next(line for line in astar_stdout.split('\n') if 'Open peak size:' in line).split('Open peak size:')[1].split(' ')[1]
                    limited_factor = float(kwargs['open_limitness'].split('limited')[1].split('-')[1])
                    kwargs['open_limit'] = str(ceil(int(value) * limited_factor / 100))
                    
                    # Retrieve second phase lower bound if needed
                    if 'pebound' in kwargs['open_limitness']:
                        reference_common_kwargs = copy.deepcopy(common_kw)
                        reference_common_kwargs['algorithm'] = 'pe-edd-eh'
                        reference_common_kwargs['open_limitness'] = f'limited-{kwargs["open_limitness"].split("-")[3]}'
                        reference_pack = get_pack(reference_common_kwargs)
                        ref_out_path = f'./tests/baseline_results/{reference_pack}/{domain}_{instance_pddl}.out'
                        if not os.path.exists(ref_out_path):
                            continue
                        reference_data = open(ref_out_path).read()
                        if 'Mininum F-value at phase transition:' in reference_data:
                            kwargs['second_phase_lower_bound'] = next(line for line in reference_data.split('\n') if 'Mininum F-value at phase transition:' in line).split('Mininum F-value at phase transition:')[1].split(' ')[1]
                        else:
                            kwargs['second_phase_lower_bound'] = next(line for line in reference_data.split('\n') if 'Plan cost:' in line).split('Plan cost:')[1].split(' ')[1]
                            
                    cmd = generate_command(kwargs)
                    all_commands.append(cmd)
                except Exception as e:
                    continue
                    
    print(f"Total commands generated: {len(all_commands)}")
    
    # Split into 3 files of max 999 lines
    chunk_size = 999
    for i in range(0, len(all_commands), chunk_size):
        chunk = all_commands[i:i+chunk_size]
        filename = f"jobs_{(i // chunk_size) + 1}.txt"
        with open(filename, "w") as f:
            f.write("\n".join(chunk) + "\n")
        print(f"Wrote {len(chunk)} commands to {filename}")
        
    # Generate optimized run_array.sbatch automatically
    sbatch_content = """#!/bin/bash
#SBATCH --partition=main
#SBATCH --time=9:00:00
#SBATCH --job-name=pea_ida_array
#SBATCH --output=logs/array_%A_%a.out
#SBATCH --error=logs/array_%A_%a.err
#SBATCH --mail-user=saarbu@post.bgu.ac.il
#SBATCH --mail-type=FAIL
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1

if [ -z "$1" ]; then
    echo "Usage: sbatch --array=1-N run_array.sbatch <jobs_file.txt>"
    exit 1
fi

JOBS_FILE=$1
mkdir -p logs

module load anaconda
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate build_env

# Extract command for this task ID (1-indexed)
CMD=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$JOBS_FILE")

if [ -z "$CMD" ]; then
    echo "Error: No command found at line ${SLURM_ARRAY_TASK_ID} in ${JOBS_FILE}"
    exit 1
fi

echo "Task ID: ${SLURM_ARRAY_TASK_ID}"
echo "Running command: ${CMD}"
echo "----------------------------------------"

eval "$CMD"
"""
    with open('run_array.sbatch', 'w') as f:
        f.write(sbatch_content)
    print("Automatically updated run_array.sbatch with optimized 9-hour limit.")

if __name__ == "__main__":
    main()
