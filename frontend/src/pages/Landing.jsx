import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <div className="landing">
      {/* Hero */}
      <section className="hero">
        <div className="hero-content">
          <div className="hero-badge">✦ Automated Profile Management</div>
          <h1>Keep your Naukri profile <span className="text-gradient">fresh, always.</span></h1>
          <p className="hero-subtitle">
            Automatically refresh your resume, rotate headlines, and swap summaries 
            every hour — so recruiters always see an active profile.
          </p>
          <div className="hero-actions">
            <Link to="/register" className="btn btn-primary btn-lg">Get Started — Free</Link>
            <a href="#features" className="btn btn-ghost btn-lg">See How It Works ↓</a>
          </div>
          <p className="hero-note">No credit card required. Set up in 2 minutes.</p>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="features">
        <h2 className="section-title">Everything runs on autopilot</h2>
        <p className="section-subtitle">Set it once, forget it forever. Your profile stays fresh 24/7.</p>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">📄</div>
            <h3>Resume Re-upload</h3>
            <p>Your resume is re-uploaded every hour from Google Drive, bumping the "last updated" timestamp that recruiters filter by.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">✏️</div>
            <h3>Headline Rotation</h3>
            <p>Alternate between two headlines each cycle. Naukri treats this as a profile change, boosting your search ranking.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon">🔄</div>
            <h3>Summary Swap</h3>
            <p>Two versions of your profile summary rotate automatically — keeping your profile dynamic and keyword-rich.</p>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="how-it-works">
        <h2 className="section-title">How it works</h2>
        <div className="steps">
          <div className="step">
            <div className="step-number">1</div>
            <h3>Create an account</h3>
            <p>Sign up in seconds. No Naukri login needed yet.</p>
          </div>
          <div className="step">
            <div className="step-number">2</div>
            <h3>Enter your Naukri details</h3>
            <p>Add your Naukri email, password, resume link, headlines, and summaries.</p>
          </div>
          <div className="step">
            <div className="step-number">3</div>
            <h3>Sit back and relax</h3>
            <p>We refresh your profile every hour. Your visibility stays at the top.</p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <p>Built with ♥ for job seekers. NopeRi is free and open source.</p>
      </footer>
    </div>
  )
}
