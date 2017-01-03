import os
from conans.errors import ConanException, NotFoundException
from conans.model.ref import PackageReference, is_a_reference,\
    ConanFileReference
from conans.util.log import logger
import time


class ConanUploader(object):

    def __init__(self, paths, user_io, remote_proxy, search_manager, loader):
        self._paths = paths
        self._user_io = user_io
        self._remote_proxy = remote_proxy
        self._search_manager = search_manager
        self._loader = loader

    def upload_conan(self, pattern, force=False, all_packages=False, confirm=False,
                     retry=None, retry_wait=None):
        """Upload all the recipes matching 'pattern'"""
        if is_a_reference(pattern):
            ref = ConanFileReference.loads(pattern)
            export_path = self._paths.export(ref)
            if not os.path.exists(export_path):
                raise NotFoundException("There is no local conanfile exported as %s"
                                        % str(ref))
            references = [ref, ]
            confirm = True
        else:
            references = self._search_manager.search(pattern)

        for conan_ref in references:
            upload = True
            if not confirm:
                msg = "Are you sure you want to upload '%s'?" % str(conan_ref)
                upload = self._user_io.request_boolean(msg)
            if upload:
                self._upload_conan(conan_ref, force, all_packages, retry, retry_wait)

    def _upload_conan(self, conan_ref, force, all_packages, retry, retry_wait):
        """Uploads the conans identified by conan_ref"""
        if not force:
            self._check_package_date(conan_ref)

        self._user_io.out.info("Uploading %s" % str(conan_ref))
        self._remote_proxy.upload_conan(conan_ref, retry, retry_wait)

        if all_packages:
            self.check_reference(conan_ref)
            for index, package_id in enumerate(self._paths.conan_packages(conan_ref)):
                total = len(self._paths.conan_packages(conan_ref))
                self.upload_package(PackageReference(conan_ref, package_id), index + 1, total,
                                    retry, retry_wait)

    def check_reference(self, conan_reference):
        try:
            conanfile_path = self._paths.conanfile(conan_reference)
            conan_file = self._loader.load_class(conanfile_path)
        except NotFoundException:
            raise NotFoundException("There is no local conanfile exported as %s"
                                    % str(conan_reference))

        # Can't use build_policy_always here because it's not loaded (only load_class)
        if conan_file.build_policy == "always":
            raise ConanException("Conanfile has build_policy='always', "
                                 "no packages can be uploaded")

    def upload_package(self, package_ref, index=1, total=1, retry=None, retry_wait=None):
        """Uploads the package identified by package_id"""
        msg = ("Uploading package %d/%d: %s" % (index, total, str(package_ref.package_id)))
        t1 = time.time()
        self._user_io.out.info(msg)
        self._remote_proxy.upload_package(package_ref, retry, retry_wait)

        logger.debug("====> Time uploader upload_package: %f" % (time.time() - t1))

    def _check_package_date(self, conan_ref):
        try:
            remote_conan_digest = self._remote_proxy.get_conan_digest(conan_ref)
        except NotFoundException:
            return  # First upload

        local_digest = self._paths.load_manifest(conan_ref)

        if remote_conan_digest.time > local_digest.time:
            raise ConanException("Remote recipe is newer than local recipe: "
                                 "\n Remote date: %s\n Local date: %s" %
                                 (remote_conan_digest.time, local_digest.time))
