"""Cloning and browsing untrusted repositories. Nothing here executes repo code.

The facade of the repository operations: the functions the web layer calls, over the classes of the sub-packages
(model: the error and the records; address: urls, names, paths in the projects folder; git: the client, cloning, pulling;
submodules: what the project records and the download for the build; folders: listings and the file list).
"""

from verdict.repository.repo.address.names import NAME_RE, default_name
from verdict.repository.repo.address.paths import ProjectsFolder, resolve_destination, safe_path
from verdict.repository.repo.address.urls import SCP_RE, SSH_RE, ssh_target, validate_url
from verdict.repository.repo.folders.listing import list_existing, list_folders, use_existing
from verdict.repository.repo.folders.tracked import tracked_files
from verdict.repository.repo.git.clone import Cloner, clone
from verdict.repository.repo.git.client import GitClient
from verdict.repository.repo.git.failures import explain_clone_failure, is_transient
from verdict.repository.repo.git.inspector import FolderInspector
from verdict.repository.repo.git.pull import Puller, pull
from verdict.repository.repo.model.errors import RepoError
from verdict.repository.repo.model.records import RepoInfo, SubmoduleNote
from verdict.repository.repo.submodules.fetcher import MAX_SUBMODULES, SubmoduleFetcher, fetch_submodules
from verdict.repository.repo.submodules.gitmodules import empty_submodules, submodule_paths
from verdict.repository.repo.submodules.policy import HostPolicy, submodule_source
