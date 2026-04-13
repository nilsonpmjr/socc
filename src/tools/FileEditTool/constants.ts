// In its own file to avoid circular dependencies
export const FILE_EDIT_TOOL_NAME = 'Edit'

// Permission pattern for granting session-level access to the project's .socc/ folder
export const SOCC_FOLDER_PERMISSION_PATTERN = '/.socc/**'

// Permission pattern for granting session-level access to the global ~/.socc/ folder
export const GLOBAL_SOCC_FOLDER_PERMISSION_PATTERN = '~/.socc/**'

export const FILE_UNEXPECTEDLY_MODIFIED_ERROR =
  'File has been unexpectedly modified. Read it again before attempting to write it.'
