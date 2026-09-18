import re

with open('mobile/lib/features/oauth_connections/oauth_connections_screen.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import
content = content.replace("import '../../core/theme.dart';", "import '../../core/theme.dart';\nimport 'oauth_connection_service.dart';")

# Update _OAuthConnectionsScreenState
old_init = """  @override
  void initState() {
    super.initState();
    _connections = List<OAuthConnectionModel>.from(_initialConnections);
  }"""

new_init = """  bool _isLoadingAll = true;

  @override
  void initState() {
    super.initState();
    _connections = [
      const OAuthConnectionModel(provider: OAuthProvider.googleCalendar),
      const OAuthConnectionModel(provider: OAuthProvider.gmail),
      const OAuthConnectionModel(provider: OAuthProvider.github),
      const OAuthConnectionModel(provider: OAuthProvider.slack),
    ];
    _fetchConnections();
  }

  Future<void> _fetchConnections() async {
    try {
      final dbConns = await OAuthConnectionService.fetchConnections();
      setState(() {
        for (var dbConn in dbConns) {
          final index = _connections.indexWhere((c) => c.provider == dbConn.provider);
          if (index != -1) {
            _connections[index] = dbConn;
          }
        }
        _isLoadingAll = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() => _isLoadingAll = false);
      }
    }
  }"""
content = content.replace(old_init, new_init)

# Update _handleAction
old_handle = """    try {
      // D9: local mock toggle — no network call.
      // D21: replace the body of this try block with a real API call.
      await Future<void>.delayed(const Duration(milliseconds: 300));

      final index =
          _connections.indexWhere((c) => c.provider == provider);
      if (index == -1) return;

      final current = _connections[index];
      OAuthConnectionModel updated;

      if (current.isConnected) {
        // Disconnect: clear status & connectedAt
        updated = current.copyWith(clearStatus: true, clearConnectedAt: true);
      } else {
        // Connect: set active + mock scopes + now as connectedAt
        final mockScopes = _mockScopesFor(provider);
        updated = OAuthConnectionModel(
          provider: provider,
          status: OAuthStatus.active,
          scopes: mockScopes,
          connectedAt: DateTime.now(),
        );
      }

      setState(() {
        _connections[index] = updated;
      });
    }"""

new_handle = """    try {
      final index = _connections.indexWhere((c) => c.provider == provider);
      if (index == -1) return;
      final current = _connections[index];

      if (current.isConnected) {
        await OAuthConnectionService.disconnect(provider);
        setState(() {
          _connections[index] = current.copyWith(clearStatus: true, clearConnectedAt: true);
        });
      } else {
        await OAuthConnectionService.connect(provider);
        // Simulate callback for testing purposes, since url_launcher isn't here
        setState(() {
          final mockScopes = _mockScopesFor(provider);
          _connections[index] = OAuthConnectionModel(
            provider: provider,
            status: OAuthStatus.active,
            scopes: mockScopes,
            connectedAt: DateTime.now(),
          );
        });
      }
    }"""
content = content.replace(old_handle, new_handle)

# Ensure CircularProgressIndicator during load
old_build = """  @override
  Widget build(BuildContext context) {
    return Scaffold("""
new_build = """  @override
  Widget build(BuildContext context) {
    if (_isLoadingAll) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    return Scaffold("""
content = content.replace(old_build, new_build)

with open('mobile/lib/features/oauth_connections/oauth_connections_screen.dart', 'w', encoding='utf-8') as f:
    f.write(content)
