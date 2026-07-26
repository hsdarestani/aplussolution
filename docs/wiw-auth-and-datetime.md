# When I Work API context and timestamps

The integration authenticates with the configured developer key and login credentials, then resolves an authorized user context through the WIW `/2/login` response. A configured account ID is mapped to the corresponding user ID before `W-UserId` is sent to protected resources such as shifts and times.

WIW shift and attendance timestamps may arrive as ISO-8601, RFC-2822 strings such as `Tue, 28 Jul 2026 16:00:00 +0200`, or Unix timestamps. The importer accepts all three forms and stores timezone-aware datetimes.

Production deployment verifies live access to both shifts and times so a successful login token alone is not considered a healthy WIW integration.
