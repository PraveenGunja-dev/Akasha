import sys

file_path = r'd:\Akasha_Platform\frontend\src\components\sections\SimulationLab.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update steps array
old_steps = """  const steps = [
    { id: 1, label: 'Detect', status: activeStep === 1 ? 'in-progress' : activeStep > 1 ? 'completed' : 'pending' },
    { id: 2, label: 'Strategies', status: activeStep === 2 ? 'in-progress' : activeStep > 2 ? 'completed' : 'pending' },
    { id: 3, label: 'Simulate', status: activeStep === 3 ? 'in-progress' : activeStep > 3 ? 'completed' : 'pending' },
    { id: 4, label: 'Execute', status: activeStep === 4 ? 'in-progress' : activeStep > 4 ? 'completed' : 'pending' },
    { id: 5, label: 'Report', status: activeStep === 5 ? 'in-progress' : activeStep > 5 ? 'completed' : 'pending' },
  ];"""
new_steps = """  const steps = [
    { id: 1, label: 'Detect', status: activeStep === 1 ? 'in-progress' : activeStep > 1 ? 'completed' : 'pending' },
    { id: 2, label: 'Strategies', status: activeStep === 2 ? 'in-progress' : activeStep > 2 ? 'completed' : 'pending' },
    { id: 3, label: 'Execute', status: activeStep === 3 ? 'in-progress' : activeStep > 3 ? 'completed' : 'pending' },
    { id: 4, label: 'Report', status: activeStep === 4 ? 'in-progress' : activeStep > 4 ? 'completed' : 'pending' },
  ];"""
if old_steps in content:
    content = content.replace(old_steps, new_steps)
else:
    print('Failed to find steps array')

# 2. Update button
old_btn = """              {strategies.length > 0 && !isGeneratingStrategies && (
                <button
                  onClick={proceedToSimulation}
                  className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold py-4 rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 mt-auto"
                >
                  <FastForward className="w-5 h-5 fill-current" /> Proceed to Simulation
                </button>
              )}"""
new_btn = """              {strategies.length > 0 && !isGeneratingStrategies && (
                <button
                  onClick={executeStrategy}
                  className="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-bold py-4 rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 mt-auto"
                >
                  <CheckCircle2 className="w-5 h-5 fill-current" /> Execute Strategy
                </button>
              )}"""
if old_btn in content:
    content = content.replace(old_btn, new_btn)
else:
    print('Failed to find old btn')

# 3. Update executeStrategy activeStep
content = content.replace('const executeStrategy = async () => {\n    setActiveStep(4);', 'const executeStrategy = async () => {\n    setActiveStep(3);')

# 4. Update generateFinalReport activeStep
content = content.replace('const generateFinalReport = async () => {\n    setActiveStep(5);', 'const generateFinalReport = async () => {\n    setActiveStep(4);')

# 5. Update JSX conditionals
content = content.replace('{activeStep === 4 && (', '{activeStep === 3 && (')
content = content.replace('{activeStep === 5 && (', '{activeStep === 4 && (')
content = content.replace('/* STEP 4: EXECUTE */', '/* STEP 3: EXECUTE */')
content = content.replace('/* STEP 5: REPORT */', '/* STEP 4: REPORT */')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
