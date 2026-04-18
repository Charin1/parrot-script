with open("src/App.tsx", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "import { PlusIcon } from './components/icons'" in line:
        lines[i] = line.replace("import { PlusIcon }", "import { PlusIcon, MenuIcon }")
    if "const [viewMode, setViewMode] = useState<'workspace' | 'dashboard'>('workspace')" in line:
        lines[i] = "  const [viewMode, setViewMode] = useState<'workspace' | 'dashboard' | 'config'>('workspace')\n  const [sidebarOpen, setSidebarOpen] = useState(true)\n"

start_idx = -1
for i in range(len(lines)):
    if "  return (" in lines[i] and i > 300: # ensure it's the main block
        start_idx = i
        break

end_idx = -1
for i in range(len(lines) - 1, -1, -1):
    if "export default App" in lines[i]:
        end_idx = i - 1
        break

with open("new_return.txt", "r") as f:
    new_return = f.read()

new_lines = lines[:start_idx] + [new_return + "\n"] + lines[end_idx:]

with open("src/App.tsx", "w") as f:
    f.writelines(new_lines)
