#!/usr/bin/env python3
import os
import tarfile
from pathlib import Path
import shutil

def debug_tar_creation():
    print("=== Debug Tar Creation ===")
    
    # Set up paths
    agent_dir = Path.cwd()
    dist_dir = agent_dir / 'dist'
    linux_pkg_dir = dist_dir / 'uptime_agent_linux_src'
    tar_path = dist_dir / 'uptime_agent_linux_src.tar.gz'
    
    print(f"Agent dir: {agent_dir}")
    print(f"Dist dir: {dist_dir}")
    print(f"Package dir: {linux_pkg_dir}")
    print(f"Tar path: {tar_path}")
    
    # Clean up and create directories
    if linux_pkg_dir.exists():
        shutil.rmtree(linux_pkg_dir)
    linux_pkg_dir.mkdir(parents=True, exist_ok=True)
    
    if tar_path.exists():
        tar_path.unlink()
    
    # Create test files
    print("\n=== Creating test files ===")
    
    # Create agent script
    agent_script = agent_dir / 'agent_parameterized.py'
    if agent_script.exists():
        shutil.copy2(agent_script, linux_pkg_dir / 'agent_parameterized.py')
        print(f"Copied agent script: {(linux_pkg_dir / 'agent_parameterized.py').stat().st_size} bytes")
    else:
        print("WARNING: agent_parameterized.py not found!")
        return False
    
    # Create requirements.txt
    with open(linux_pkg_dir / 'requirements.txt', 'w') as f:
        f.write('psutil>=5.8.0\nrequests>=2.25.0\n')
    print(f"Created requirements.txt: {(linux_pkg_dir / 'requirements.txt').stat().st_size} bytes")
    
    # Create launcher script
    launcher_content = '''#!/bin/bash
echo "Uptime Agent Launcher"
python3 agent_parameterized.py "$@"
'''
    launcher_path = linux_pkg_dir / 'uptime_agent'
    with open(launcher_path, 'w') as f:
        f.write(launcher_content)
    launcher_path.chmod(0o755)
    print(f"Created launcher: {launcher_path.stat().st_size} bytes")
    
    # Create README
    readme_content = '''# Test README
This is a test package.
'''
    with open(linux_pkg_dir / 'README.md', 'w') as f:
        f.write(readme_content)
    print(f"Created README: {(linux_pkg_dir / 'README.md').stat().st_size} bytes")
    
    # List all files in the package directory
    print(f"\n=== Files in {linux_pkg_dir} ===")
    total_size = 0
    for file_path in linux_pkg_dir.glob('*'):
        if file_path.is_file():
            size = file_path.stat().st_size
            total_size += size
            print(f"  {file_path.name}: {size} bytes")
    print(f"Total size: {total_size} bytes")
    
    # Create tar.gz using the method in the Flask app
    print(f"\n=== Creating tar.gz ===")
    try:
        with tarfile.open(tar_path, 'w:gz') as tar:
            for file_path in linux_pkg_dir.glob('*'):
                if file_path.is_file():
                    arcname = f'uptime_agent_linux/{file_path.name}'
                    print(f"Adding {file_path} as {arcname}")
                    tar.add(file_path, arcname=arcname)
        
        # Check result
        if tar_path.exists():
            size = tar_path.stat().st_size
            print(f"SUCCESS: Created {tar_path} with size {size} bytes ({size/1024/1024:.3f} MB)")
            
            # Test extraction
            print(f"\n=== Testing extraction ===")
            test_extract_dir = dist_dir / 'test_extract'
            if test_extract_dir.exists():
                shutil.rmtree(test_extract_dir)
            test_extract_dir.mkdir()
            
            with tarfile.open(tar_path, 'r:gz') as tar:
                tar.extractall(test_extract_dir)
                
            # List extracted contents
            for extracted_file in test_extract_dir.rglob('*'):
                if extracted_file.is_file():
                    print(f"  Extracted: {extracted_file.relative_to(test_extract_dir)}")
            
            return True
        else:
            print("ERROR: Tar file not created!")
            return False
            
    except Exception as e:
        print(f"ERROR creating tar.gz: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up temp directory
        if linux_pkg_dir.exists():
            shutil.rmtree(linux_pkg_dir)

if __name__ == "__main__":
    debug_tar_creation()
