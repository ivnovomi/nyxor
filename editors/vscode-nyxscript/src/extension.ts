import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration("nyxscript");
  const command = config.get<string>("serverCommand", "nyx");
  const args = config.get<string[]>("serverArgs", ["script", "lsp"]);

  const serverOptions: ServerOptions = {
    command,
    args,
    options: {
      cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
    },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "nyxscript" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.nyx"),
    },
  };

  client = new LanguageClient(
    "nyxscript",
    "NyxScript Language Server",
    serverOptions,
    clientOptions,
  );

  client.start().catch((error: unknown) => {
    void vscode.window.showErrorMessage(
      `NyxScript: couldn't start the language server ('${command} ${args.join(" ")}'). ` +
        "Make sure NYXOR is installed with the 'lsp' extra (uv sync --extra lsp) and the " +
        'command is on PATH, or set "nyxscript.serverCommand" / "nyxscript.serverArgs" in ' +
        `your settings. (${String(error)})`,
    );
  });

  context.subscriptions.push({
    dispose: () => {
      void client?.stop();
    },
  });
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
