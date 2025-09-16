#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

def rebuild_agents():
    """Rebuild the agent executables with the fixed code."""
    print("🔄 Rebuilding agents with fixed code...")
    
    # Get the current directory
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(agent_dir, 'dist')
    
    # Clean up old builds
    print("🧹 Cleaning up old builds...")
    if os.path.exists(dist_dir):
        try:
            shutil.rmtree(dist_dir, ignore_errors=True)
        except Exception as e:
            print(f"⚠️ Warning: Could not fully clean dist directory: {e}")
    os.makedirs(dist_dir, exist_ok=True)
    
    # Clean up build cache (skip if locked)
    build_dir = os.path.join(agent_dir, 'build')
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir, ignore_errors=True)
        except Exception as e:
            print(f"⚠️ Warning: Could not clean build directory: {e}")
            print("   This is usually fine - PyInstaller will work around it.")
    
    # Path to the fixed agent script
    agent_script = os.path.join(agent_dir, 'agent_parameterized.py')
    
    if not os.path.exists(agent_script):
        print(f"❌ Error: {agent_script} not found!")
        return False
    
    print(f"📄 Using script: {agent_script}")
    
    try:
        # Install required packages
        print("📦 Installing required packages...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller', 'psutil', 'requests'], 
                      check=True, capture_output=True)
        
        # Build Windows executable
        print("🏗️ Building Windows executable...")
        pyinstaller_cmd = [
            sys.executable, '-m', 'PyInstaller',
            '--onefile',
            '--name', 'uptime_agent',
            '--distpath', dist_dir,
            '--clean',
            '--noconfirm',
            agent_script
        ]
        
        print(f"Running: {' '.join(pyinstaller_cmd)}")
        result = subprocess.run(pyinstaller_cmd, cwd=agent_dir, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("❌ Build failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
        
        # Check if executable was created
        exe_path = os.path.join(dist_dir, 'uptime_agent.exe')
        if os.path.exists(exe_path):
            print(f"✅ Windows executable created: {exe_path}")
            print(f"📏 File size: {os.path.getsize(exe_path) / (1024*1024):.1f} MB")
        else:
            print("❌ Windows executable not found after build!")
            return False
            
        print("🎉 Agent rebuild completed successfully!")
        print(f"📁 Executable location: {exe_path}")
        print("\n🔧 Test the new agent with:")
        print(f"   {exe_path} --monitor-id 3 --api-endpoint http://127.0.0.1:5000/api")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with error: {e}")
        if hasattr(e, 'stdout') and e.stdout:
            print("STDOUT:", e.stdout)
        if hasattr(e, 'stderr') and e.stderr:
            print("STDERR:", e.stderr)
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == '__main__':
    success = rebuild_agents()
    if success:
        print("\n✨ Ready to test! The new agent should now respect the --api-endpoint parameter.")
    else:
        print("\n💥 Build failed. Please check the errors above.")
    
    input("\nPress Enter to exit...")
