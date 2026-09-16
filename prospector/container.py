"""Monta as pecas do sistema (usado pelo CLI e pelo painel)."""
import os
from functools import cached_property

from prospector.adapters.autofill.browser import AutofillWorker, BrowserSession, playwright_available
from prospector.adapters.http import default_client
from prospector.adapters.jd_fetcher import JobDescriptionFetcher
from prospector.adapters.llm_anthropic import AnthropicClient
from prospector.adapters.miners import build_miners
from prospector.adapters.pdf_chrome import ChromePdfRenderer
from prospector.core import config
from prospector.core.db import get_repository
from prospector.profile import load_profile
from prospector.services.application import ApplicationService
from prospector.services.apply_flow import ApplyFlow
from prospector.services.mining import MiningService
from prospector.services.outreach import OutreachService
from prospector.services.resume_import import ResumeImportService
from prospector.services.resume_store import ResumeStore

APPLICATIONS_DIR = os.path.join(config.DATA_DIR, "applications")
BROWSER_PROFILE_DIR = os.path.join(config.DATA_DIR, "browser-profile")


class Container:
    def __init__(self, repo=None, use_browser=True):
        config.load_env()
        self._repo = repo
        self.use_browser = use_browser

    @cached_property
    def repo(self):
        return self._repo or get_repository()

    @cached_property
    def profile(self):
        return load_profile()

    @cached_property
    def http(self):
        return default_client()

    @cached_property
    def llm(self):
        return AnthropicClient(model=self.profile.model or None)

    @cached_property
    def resume_store(self):
        return ResumeStore(self.profile.master_resume_path)

    @cached_property
    def pdf_renderer(self):
        return ChromePdfRenderer(self.profile.chrome_path)

    @cached_property
    def jd_fetcher(self):
        return JobDescriptionFetcher(self.http)

    @cached_property
    def applications(self):
        return ApplicationService(self.repo, self.profile, self.resume_store, self.llm,
                                  self.jd_fetcher, self.pdf_renderer, APPLICATIONS_DIR)

    @cached_property
    def importer(self):
        return ResumeImportService(self.llm, self.resume_store, self.profile)

    @cached_property
    def outreach(self):
        return OutreachService(self.repo, self.profile)

    @cached_property
    def miners(self):
        return build_miners(self.http, sources=self.profile.fontes)

    @cached_property
    def mining(self):
        return MiningService(self.miners, self.repo)

    @cached_property
    def browser_available(self):
        return self.use_browser and playwright_available()

    @cached_property
    def browser_session(self):
        return BrowserSession(BROWSER_PROFILE_DIR, chrome_path=self.profile.chrome_path)

    @cached_property
    def autofill_worker(self):
        return AutofillWorker(self.browser_session) if self.browser_available else None

    @cached_property
    def apply_flow(self):
        return ApplyFlow(self.applications, self.profile, self.resume_store, worker=self.autofill_worker)
