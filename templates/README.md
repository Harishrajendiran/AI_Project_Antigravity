# Templates Directory

This directory contains the Jinja2 HTML templates used by the SmashHard Badminton Tournament application to render pages dynamically. All templates incorporate secure coding practices, modern premium UI styles, and responsive layouts.

## Directory Structure & Files

- **[login.html](file:///c:/Users/91956/Documents/GitHub/AI_Project_Antigravity/templates/login.html)**: 
  The entry sign-in page. Rendered when users access the application root `/`. It integrates secure backend validation, custom CSRF protection, and displays feedback/error messages using flash blocks.
  
- **[register.html](file:///c:/Users/91956/Documents/GitHub/AI_Project_Antigravity/templates/register.html)**: 
  The new user registration page. It collects registration details (name, email, mobile, and password) and loads dynamic validation scripts to enforce formatting before submission.
  
- **[dashboard.html](file:///c:/Users/91956/Documents/GitHub/AI_Project_Antigravity/templates/dashboard.html)**: 
  The secure main dashboard displaying user profile information (with masked PII) and a listing of all active and historical tournaments.
  
- **[create_tournament.html](file:///c:/Users/91956/Documents/GitHub/AI_Project_Antigravity/templates/create_tournament.html)**: 
  Step 1 of the tournament generation wizard. Allows administrators and users to define the tournament name, entry deadline, and toggle open registrations.
  
- **[select_fixture.html](file:///c:/Users/91956/Documents/GitHub/AI_Project_Antigravity/templates/select_fixture.html)**: 
  Step 2 of the tournament wizard. Provides options to choose the fixture formats, setup rounds, and group teams.
  
- **[tournament_detail.html](file:///c:/Users/91956/Documents/GitHub/AI_Project_Antigravity/templates/tournament_detail.html)**: 
  The comprehensive view of a single tournament. It showcases groups, standings, schedules, round details, and permits match scores editing or updates dynamically.

---

## Design and Integration

- **Styling**: All templates reference the global stylesheet located at `/static/style.css` which implements modern Outfit typography, glassmorphism, responsive container grids, and custom background gradient animations.
- **Client Logic**: Interactive pages import target Javascript logic files from `/static` (e.g., `login.js`, `register.js`, `tournament.js`) for immediate responsiveness and client-side formatting checks.
- **Security**: Forms utilize strict POST submission and inject `{{ csrf_token }}` values to prevent Cross-Site Request Forgery (CSRF) vulnerabilities.
