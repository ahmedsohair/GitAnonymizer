import { useEffect, useMemo, useState } from "react";

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Request failed");
  }
  return response.json();
}

function getPageFromHash() {
  const hash = window.location.hash.replace(/^#\/?/, "").toLowerCase();
  if (hash.startsWith("dashboard")) {
    return "dashboard";
  }
  if (hash.startsWith("anonymize")) {
    return "anonymize";
  }
  return "home";
}

export function App() {
  const [page, setPage] = useState(getPageFromHash());
  const [sourceUrl, setSourceUrl] = useState("");
  const [terms, setTerms] = useState("");
  const [mirrors, setMirrors] = useState([]);
  const [stats, setStats] = useState({
    mirrors_total: 0,
    mirrors_ready: 0,
    mirrors_failed: 0,
    jobs_queued: 0,
    jobs_running: 0
  });
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [createdMirror, setCreatedMirror] = useState(null);
  const [copiedToken, setCopiedToken] = useState(null);

  const loadData = async (showSpinner = false) => {
    if (showSpinner) {
      setRefreshing(true);
    }
    try {
      const [mirrorData, statsData] = await Promise.all([api("/mirrors"), api("/stats")]);
      setMirrors(mirrorData);
      setStats(statsData);
    } catch (e) {
      setError(String(e.message));
    } finally {
      if (showSpinner) {
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    loadData(true);
  }, []);

  useEffect(() => {
    const onHashChange = () => setPage(getPageFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const createMirror = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setCreatedMirror(null);
    try {
      const result = await api("/mirrors", {
        method: "POST",
        body: JSON.stringify({ source_url: sourceUrl })
      });
      setCreatedMirror(result.mirror);
      setSourceUrl("");
      setTerms("");
      await loadData();
      window.location.hash = "/dashboard";
    } catch (e) {
      setError(String(e.message));
    } finally {
      setLoading(false);
    }
  };

  const triggerSync = async (id) => {
    setError("");
    try {
      await api(`/mirrors/${id}/sync`, { method: "POST" });
      await loadData();
    } catch (e) {
      setError(String(e.message));
    }
  };

  const renewUrl = async (id) => {
    setError("");
    try {
      await api(`/mirrors/${id}/renew-url`, { method: "POST" });
      await loadData();
    } catch (e) {
      setError(String(e.message));
    }
  };

  const filteredMirrors = useMemo(() => {
    return mirrors.filter((mirror) => {
      if (statusFilter !== "all" && mirror.status !== statusFilter) {
        return false;
      }
      if (!search.trim()) {
        return true;
      }
      const query = search.trim().toLowerCase();
      return (
        String(mirror.id).includes(query) ||
        mirror.source_url.toLowerCase().includes(query) ||
        mirror.public_token.toLowerCase().includes(query)
      );
    });
  }, [mirrors, statusFilter, search]);

  const go = (targetPage) => {
    window.location.hash = `/${targetPage}`;
  };

  const buildPublicLink = (token) => `${window.location.origin}/r/${token}/browse`;

  const copyPublicLink = async (token) => {
    const url = buildPublicLink(token);
    try {
      await navigator.clipboard.writeText(url);
      setCopiedToken(token);
      setTimeout(() => {
        setCopiedToken((prev) => (prev === token ? null : prev));
      }, 1600);
    } catch (e) {
      setError("Unable to copy link automatically. Copy it manually from the Open link.");
    }
  };

  const renderHome = () => (
    <>
      <section className="hero">
        <div className="hero-content">
          <h1>VeilMirror Core v2</h1>
          <p>
            Publish privacy-safe repository mirrors for blind review with one click, then keep them
            manually synced.
          </p>
          <div className="hero-actions">
            <button className="button-primary" onClick={() => go("anonymize")}>
              Anonymize Repository
            </button>
            <button className="button-secondary" onClick={() => go("dashboard")}>
              Open Dashboard
            </button>
          </div>
        </div>
      </section>

      <section className="section-card">
        <h2>Usage</h2>
        <ol>
          <li>Paste a public GitHub repository URL and create a mirror.</li>
          <li>Wait for anonymization to finish and copy the generated `/r/{`"{token}"`}` link.</li>
          <li>Use manual sync whenever the source repository changes.</li>
        </ol>
      </section>

      <section className="feature-grid">
        <article className="feature">
          <h3>Double-Anonymous Ready</h3>
          <p>Repository URL and author-related terms are redacted before publication.</p>
        </article>
        <article className="feature">
          <h3>Sharable Explorer Link</h3>
          <p>Reviewers browse an anonymized mirror at a unique URL path: `/r/&lt;token&gt;`.</p>
        </article>
        <article className="feature">
          <h3>Simple Operations</h3>
          <p>Renew public URL tokens and manually trigger sync runs from a single dashboard.</p>
        </article>
      </section>

      <section className="metrics">
        <div className="metric-box">
          <span className="metric-value">{stats.mirrors_total}</span>
          <span className="metric-label">Mirrors</span>
        </div>
        <div className="metric-box">
          <span className="metric-value">{stats.mirrors_ready}</span>
          <span className="metric-label">Ready</span>
        </div>
        <div className="metric-box">
          <span className="metric-value">{stats.jobs_running + stats.jobs_queued}</span>
          <span className="metric-label">Active Jobs</span>
        </div>
      </section>
    </>
  );

  const renderAnonymize = () => (
    <section className="section-card anonymize-panel">
      <h2>Anonymize Repository</h2>
      <p className="hint">Create an anonymized mirror from a public GitHub repository URL.</p>
      <form onSubmit={createMirror}>
        <label htmlFor="source_url">GitHub Repository URL</label>
        <input
          id="source_url"
          type="url"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          placeholder="https://github.com/org/repo"
          required
        />

        <label htmlFor="terms">Terms to anonymize (optional notes)</label>
        <textarea
          id="terms"
          rows="4"
          value={terms}
          onChange={(e) => setTerms(e.target.value)}
          placeholder={"one term per line\norganization-name\nlab-name"}
        />
        <small className="hint">
          Core runtime remains intentionally lightweight. For full enterprise workflows, use the Advanced stack.
        </small>

        <div className="form-actions">
          <button type="submit" className="button-primary" disabled={loading}>
            {loading ? "Creating..." : "Anonymize"}
          </button>
          <button type="button" className="button-secondary" onClick={() => go("dashboard")}>
            Go to Dashboard
          </button>
        </div>
      </form>

      {createdMirror && (
        <div className="success">
          Mirror created.
          <div className="link-row">
            <a href={`/r/${createdMirror.public_token}/browse`} target="_blank" rel="noreferrer">
              /r/{createdMirror.public_token}/browse
            </a>
            <button
              type="button"
              className="copy-btn"
              onClick={() => copyPublicLink(createdMirror.public_token)}
            >
              {copiedToken === createdMirror.public_token ? "Copied" : "Copy Link"}
            </button>
          </div>
        </div>
      )}
    </section>
  );

  const renderDashboard = () => (
    <section className="section-card">
      <div className="dashboard-header">
        <h2>Repositories Dashboard</h2>
        <button className="button-secondary" onClick={() => loadData(true)}>
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <div className="filters">
        <input
          type="search"
          placeholder="Find by id, source URL, or token"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>
          <option value="ready">Ready</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {filteredMirrors.length === 0 ? (
        <p className="hint">No repositories match your filters.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Source</th>
              <th>Public</th>
              <th>Expires</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredMirrors.map((mirror) => {
              const publicUrl = `/r/${mirror.public_token}/browse`;
              return (
                <tr key={mirror.id}>
                  <td>r-{mirror.id}</td>
                  <td>
                    <span className={`status status-${mirror.status}`}>{mirror.status}</span>
                  </td>
                  <td className="source">{mirror.source_url}</td>
                  <td>
                    <div className="link-row">
                      <a href={publicUrl} target="_blank" rel="noreferrer">
                        Open
                      </a>
                      <button
                        type="button"
                        className="copy-btn"
                        onClick={() => copyPublicLink(mirror.public_token)}
                      >
                        {copiedToken === mirror.public_token ? "Copied" : "Copy Link"}
                      </button>
                    </div>
                  </td>
                  <td>{new Date(mirror.expires_at).toLocaleDateString()}</td>
                  <td className="actions">
                    <button onClick={() => triggerSync(mirror.id)}>Sync</button>
                    <button onClick={() => renewUrl(mirror.id)}>Renew URL</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        <a href="#/home" className="brand">
          VeilMirror Core
        </a>
        <nav>
          <button className={page === "home" ? "active" : ""} onClick={() => go("home")}>
            Home
          </button>
          <button className={page === "anonymize" ? "active" : ""} onClick={() => go("anonymize")}>
            Anonymize
          </button>
          <button className={page === "dashboard" ? "active" : ""} onClick={() => go("dashboard")}>
            Dashboard
          </button>
          <a className="top-link" href="http://localhost:5000" target="_blank" rel="noreferrer">
            Advanced
          </a>
        </nav>
      </header>

      <div className="container">
        {page === "home" && renderHome()}
        {page === "anonymize" && renderAnonymize()}
        {page === "dashboard" && renderDashboard()}
      </div>
      {error && <div className="error">{error}</div>}
    </main>
  );
}

