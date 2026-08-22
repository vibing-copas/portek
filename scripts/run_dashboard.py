import os
import sys
import subprocess

def check_and_install_dependencies():
    required = ["fastapi", "uvicorn"]
    missing = []
    for pkg in required:
        try:
            if pkg == "fastapi":
                import fastapi
            elif pkg == "uvicorn":
                import uvicorn
        except ImportError:
            missing.append(pkg)
            
    if missing:
        print(f"[~] Missing dependencies for custom web server: {missing}")
        print("[~] Installing dependencies in virtual environment...")
        try:
            # Determine path to pip inside virtualenv
            if sys.platform == "win32":
                pip_path = os.path.join(os.path.dirname(sys.executable), "pip.exe")
            else:
                pip_path = os.path.join(os.path.dirname(sys.executable), "pip")
                
            if os.path.exists(pip_path):
                subprocess.run([pip_path, "install"] + missing, check=True)
            else:
                subprocess.run([sys.executable, "-m", "pip", "install"] + missing, check=True)
            print("[+] Dependencies installed successfully!")
        except Exception as e:
            print(f"[-] Failed to install dependencies: {e}")
            sys.exit(1)

if __name__ == "__main__":
    # Ensure project root is in python path
    project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        
    check_and_install_dependencies()
    
    import uvicorn
    print("[+] Starting Carbon Vortex custom dashboard server...")
    print("[+] Open your browser at http://localhost:8000")
    
    # Run the uvicorn server pointing to our server app
    uvicorn.run("carbon_tracker.ui.server:app", host="0.0.0.0", port=8000, reload=True)
