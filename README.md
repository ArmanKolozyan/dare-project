# Decentralised Access Control Algorithms

This repository contains the implementation of decentralised access control mechanisms as part of the project for the **DARE 2024 Summer School**. The project, developed by Arman Kolozyan and Jolien Andries, compares two distinct algorithms: the **Matrix Power Level Model** and the **Seniority-Based Access Control Algorithm**. 

1. **Matrix's Power Level Model**:
   - Role-based hierarchy with levels (User, Moderator, Administrator).
   - Conflict resolution using deterministic operations in a hash graph.

2. **Seniority-Based Model**:
   - Total ordering of devices based on seniority.
   - Depth-first traversal for validating operations.

3. **Bonus**:
   - Integration of application messages into access control logic.
   - Comprehensive test suite for basic and edge cases.
   - Property-based testing.

## Repository Structure

- `project-power-level-based.py`: Implementation of the access control algorithm using the Matrix Power Level Model.
- `project-seniority-ranking-based.py`: Implementation of the access control algorithm based on the Seniority Ranking Model.
- `requirements.txt`: List of required Python libraries and dependencies for the project.
- `README.md`: This file.

## Getting Started

1. Clone the repository:
   ```bash
   git clone https://github.com/ArmanKolozyan/dare-project.git
   cd dare-project
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run tests for the Matrix Power Level Model:
   ```bash
   python project-power-level-based.py
   ```

4. Run tests for the Seniority Ranking Model:
   ```bash
   python project-seniority-ranking-based.py
   ```