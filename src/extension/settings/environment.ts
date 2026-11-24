// Where the editor is told to find things: the environment of the editor container (docker-compose and the image set it).

export interface Settings {
  apiUrl: string;           // the web app
  projectsDir: string;      // the folder of the projects under review
  reportsRoot: string;      // where claude saves its report: <here>/<session>/claude-review.md
}

export function readSettings(env: NodeJS.ProcessEnv = process.env): Settings {
  return {
    apiUrl: (env.VERDICT_API || "http://web:8000").replace(/\/$/, ""),
    projectsDir: env.PROJECTS_DIR || "/projects",
    reportsRoot: (env.REPORTS_ROOT || "/scratch/reports").replace(/\/$/, ""),
  };
}
