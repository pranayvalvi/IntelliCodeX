@echo off
setlocal
color 0A

echo ===============================================================================
echo Intelli-Codex: A Distributed AI Framework for Intelligent Software Maintenance
echo Final Year Project Demonstration
echo ===============================================================================
echo.
echo Press any key to run the Phase 7 Experimental Benchmark...
pause >nul
cls

echo [1/3] Running Empirical Hybrid Ranking vs RRF Benchmark...
.\.venv\Scripts\python.exe scripts\evaluate_ranking.py
echo.
echo Press any key to start the Interactive RAG Session (AlphaBetaGamma Enabled)...
pause >nul
cls

echo [2/3] Starting Interactive CLI with Hybrid Ranking...
echo (Type 'exit' to quit the interactive prompt when finished)
echo.
.\.venv\Scripts\python.exe cli.py sample_repo
echo.
echo Press any key to start the Interactive RAG Session (RRF Baseline Mode)...
pause >nul
cls

echo [3/3] Starting Interactive CLI in Legacy Baseline Mode...
echo (Type 'exit' to quit the interactive prompt when finished)
echo.
.\.venv\Scripts\python.exe cli.py sample_repo --no-hybrid
echo.
echo ===============================================================================
echo Final Demonstration Concluded. Thank you!
echo ===============================================================================
pause
