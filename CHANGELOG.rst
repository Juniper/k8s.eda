===================================================
Junipernetworks EDA source Collection Release Notes
===================================================

.. contents:: Topics

v1.4.4
=======

Minor Changes
-------------

- Explicitly set base image version.

v1.4.3
=======

Minor Changes
-------------

- Update python dependencies.
- Log when test event count is reached.

v1.4.2
=======

Minor Changes
-------------

- Change default heartbeat interval to 30 seconds.

v1.4.1
=======

Minor Changes
-------------

- Fix links in documentation.
- Repackage.

v1.4.0
=======

Major Changes
-------------

- Change namespace to juniper.
- Add image build support.

v1.3.1
=======

Minor Changes
-------------

- Fix issue with igore_modified_deleted check not happening if changed_fields is set.
- Fix "make test" target.

v1.3.0
=======

Major Changes
-------------

- Add optional support for ignoring modified/deleted events.
- Always skip queueing duplicate events (events that have the same resource version).

v1.2.0
=======

Major Changes
-------------

- Add support for filtering MODIFIED events by specific fields.
- Add decision environment image build.

v1.1.13
=======

Minor Changes
-------------

- Updated documentation.

v1.1.12
=======

Major Changes
-------------

- Add support for watching multiple resources.
- INIT_DONE event now includes all resources from get before watch in a resource list.
  * Initiaze watches in the order they appear in the configuration.
  * Start watching all types in parallel.

v1.0.57
=======

Major Changes
-------------

- Handle pre-existing matching events on startup.
- Add heartbeat to K8s source.
- More robust handling of resource versions.
- Unit tests based on kind.
- Avoid 410 errors from watch API.
- Improve test coverage.
- Fix events not being processed when the source is started.
- Remove extra files from packaging.
- Use asynchronous Kubernetes API.
- Include stack traces upon error.
