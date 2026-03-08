declare module 'sql.js/dist/sql-asm.js' {
  type SqlJsModule = {
    Database: new (data?: Uint8Array) => {
      run: (sql: string, params?: unknown[] | Record<string, unknown>) => void
      exec: (sql: string, params?: unknown[] | Record<string, unknown>) => Array<{ columns: string[]; values: unknown[][] }>
      export: () => Uint8Array
      close: () => void
    }
  }

  const initSqlJs: (config?: Record<string, unknown>) => Promise<SqlJsModule>
  export default initSqlJs
}

declare module 'sql.js' {
  type SqlJsModule = {
    Database: new (data?: Uint8Array) => {
      run: (sql: string, params?: unknown[] | Record<string, unknown>) => void
      exec: (sql: string, params?: unknown[] | Record<string, unknown>) => Array<{ columns: string[]; values: unknown[][] }>
      export: () => Uint8Array
      close: () => void
    }
  }

  const initSqlJs: (config?: { locateFile?: (file: string) => string }) => Promise<SqlJsModule>
  export default initSqlJs
}
