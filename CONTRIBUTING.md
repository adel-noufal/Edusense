# Contributing to EduSense 🎓

Thank you for your interest in contributing to **EduSense — Multi-Agent AI Education Platform**!

👤 **Author & Maintainer:** [Adel Mohamed Noufal](https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/)

---

## 🚀 Getting Started

1. **Fork the Repository**: Click the **Fork** button at the top right of [adel-noufal/Edusense](https://github.com/adel-noufal/Edusense).
2. **Clone your Fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Edusense.git
   cd Edusense
   ```
3. **Set Up Local Environment**:
   - Backend:
     ```bash
     cd backend
     python -m venv .venv
     .venv\Scripts\activate
     pip install -r requirements.txt
     ```
   - Frontend:
     ```bash
     cd frontend
     npm install
     npm run dev
     ```

---

## 🛠️ Code Conventions

- **Python (Backend)**: Follow PEP8 coding guidelines. Keep imports clean and type hints explicit.
- **AI Agents**: Implement agents inside `backend/app/agents/`. Every agent must inherit from `base.py` standards and utilize `generate_json_any` for multi-tier provider fallback.
- **Frontend (React)**: Use functional components, TailwindCSS utility classes, and reusable React hooks.

---

## 📬 Pull Request Guidelines

1. Create a feature branch: `git checkout -b feature/my-new-feature`.
2. Commit your changes with clear, descriptive commit messages.
3. Ensure CI checks pass by verifying python compilation (`py_compile`) and Vite frontend build (`npm run build`).
4. Push to your branch and submit a Pull Request to `adel-noufal/Edusense:main`.

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
