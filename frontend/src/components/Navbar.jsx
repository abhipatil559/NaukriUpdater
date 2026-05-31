import { Link, useNavigate } from 'react-router-dom'
import { isLoggedIn, logout } from '../api'

export default function Navbar() {
  const navigate = useNavigate()
  const loggedIn = isLoggedIn()

  function handleLogout() {
    logout()
    navigate('/')
    window.location.reload()
  }

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="navbar-brand">
          <span className="brand-icon">◈</span>
          NopeRi
        </Link>
        <div className="navbar-links">
          {loggedIn ? (
            <>
              <Link to="/dashboard" className="nav-link">Dashboard</Link>
              <button onClick={handleLogout} className="btn btn-ghost">Logout</button>
            </>
          ) : (
            <>
              <Link to="/login" className="nav-link">Login</Link>
              <Link to="/register" className="btn btn-primary">Get Started</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}
