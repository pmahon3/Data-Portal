import "./ProjectManagement.css";
import axios from "axios";
import { useEffect, useState } from "react";
import { useKeycloak } from "@react-keycloak/web";
import { formatError } from "../../../utils/errorUtils";
import { getAuthHeaders } from "../../../utils/authUtils";
import ProjectCard from "./ProjectCard";
import ProjectForm from "./ProjectForm";
import ProjectModal from "./ProjectModal";

const http = axios.create({ baseURL: "/api" });

export default function ProjectManagement() {
  const { keycloak, initialized } = useKeycloak();
  const roles = keycloak?.tokenParsed?.realm_access?.roles || [];
  const isAdmin = roles.includes("admin");

  // List of projects that are visible to the current logged in user
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingProjectName, setDeletingProjectName] = useState("");
  const [err, setErr] = useState("");

  // Keep track of which project to open a modal for
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const selectedProject =
    projects.find(project => project.name === selectedProjectId) || null;

  async function loadProjects() {
    const headers = await getAuthHeaders();
    const { data } = await http.get("/projects", { headers });
    setProjects(Array.isArray(data) ? data : []);
  }

  useEffect(() => {
    (async () => {
      if (!initialized) return;
      try {
        await loadProjects();
      } catch (e) {
        setErr(formatError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [initialized]);

  async function createProject(payload) {
    setErr("");
    setCreating(true);
    try {
      const headers = await getAuthHeaders();
      const { data: createdProject } = await http.post("/projects", payload, { headers });
      setProjects(prev => [createdProject, ...prev]);
    } catch (e) {
      setErr(formatError(e));
      throw e;
    } finally {
      setCreating(false);
    }
  }

  async function deleteProject(project) {
    if (!window.confirm(`Delete project "${project.name}"?`)) return;

    setErr("");
    setDeletingProjectName(project.name);
    try {
      const headers = await getAuthHeaders();
      await http.delete(`/projects/${encodeURIComponent(project.name)}`, { headers });

      setProjects(prev => prev.filter(item => item.name !== project.name));
      if (selectedProjectId === project.name) {
        setSelectedProjectId(null);
      }
    } catch (e) {
      setErr(formatError(e));
    } finally {
      setDeletingProjectName("");
    }
  }

  function handleManage(project) {
    setSelectedProjectId(project.name);
  }

  function replaceProject(nextProject) {
    setProjects(prev => prev.map(project =>
      project.name === nextProject.name ? { ...project, ...nextProject } : project
    ));
  }

  async function updateSelectedProject(nextProject) {
    const currentProject = selectedProject;
    const headers = await getAuthHeaders();
    const projectName = encodeURIComponent(currentProject.name);
    const change = (field) => ({
      added: nextProject[field].find(name => !currentProject[field].includes(name)),
      removed: currentProject[field].find(name => !nextProject[field].includes(name)),
    });
    const userChange = change("users");
    const managerChange = change("managers");
    const storageInstanceChange = change("storageInstances");

    try {
      let response;
      if (userChange.added) {
        response = await http.post(`/projects/${projectName}/users`, { username: userChange.added }, { headers });
      } else if (userChange.removed) {
        response = await http.delete(`/projects/${projectName}/users/${encodeURIComponent(userChange.removed)}`, { headers });
      } else if (managerChange.added) {
        response = await http.post(`/projects/${projectName}/managers`, { username: managerChange.added }, { headers });
      } else if (managerChange.removed) {
        response = await http.delete(`/projects/${projectName}/managers/${encodeURIComponent(managerChange.removed)}`, { headers });
      } else if (storageInstanceChange.added) {
        response = await http.post(`/projects/${projectName}/storage-instances`, { instance_name: storageInstanceChange.added }, { headers });
      } else if (storageInstanceChange.removed) {
        response = await http.delete(`/projects/${projectName}/storage-instances/${encodeURIComponent(storageInstanceChange.removed)}`, { headers });
      }

      replaceProject(response?.data || nextProject);
    } catch (e) {
      const message = formatError(e);
      setErr(message);
      throw new Error(message);
    }
  }

  return (
    <div className="pm-root">
      <h1>Project Management</h1>

      {err && <div className="pm-error">{err}</div>}

      {isAdmin && <ProjectForm onCreate={createProject} creating={creating} />}

      <section className="pm-grid">
        {loading ? (
          <div className="pm-card">
            <p className="pm-muted">Loading projects...</p>
          </div>
        ) : projects.length === 0 ? (
          <div className="pm-card">
            <p className="pm-muted">No projects found.</p>
          </div>
        ) : (
          projects.map(project => (
            <ProjectCard
              key={project.name}
              project={project}
              deleting={deletingProjectName === project.name}
              onManage={() => handleManage(project)}
              onDelete={isAdmin ? () => deleteProject(project) : null}
            />
          ))
        )}
      </section>

      {selectedProject && (
        <ProjectModal
          project={selectedProject}
          onClose={() => setSelectedProjectId(null)}
          onUpdate={updateSelectedProject}
          isAdmin={isAdmin}
        />
      )}
    </div>
  );
}
