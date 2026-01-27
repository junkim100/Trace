import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import type {
  Conversation,
  ConversationMessage,
  ConversationSendResponse,
} from '../types/trace-api';

interface ConversationState {
  conversations: Conversation[];
  currentConversationId: string | null;
  // Messages keyed by conversation ID for persistence across switches
  messagesByConversation: Record<string, ConversationMessage[]>;
  loading: boolean;
  error: string | null;
  hasMoreMessages: boolean;
  // Track which conversations have pending requests
  pendingConversations: Set<string>;
}

interface ConversationContextType {
  // Computed values
  conversations: Conversation[];
  currentConversation: Conversation | null;
  messages: ConversationMessage[];
  loading: boolean;
  sending: boolean; // True if current conversation has pending request
  error: string | null;
  hasMoreMessages: boolean;
  // Check if a specific conversation is generating
  isConversationPending: (conversationId: string) => boolean;
  // Actions
  loadConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation | null>;
  selectConversation: (conversationId: string) => Promise<void>;
  sendMessage: (query: string, options?: SendMessageOptions) => Promise<ConversationSendResponse | null>;
  renameConversation: (conversationId: string, title: string) => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  togglePin: (conversationId: string) => Promise<void>;
  archiveConversation: (conversationId: string) => Promise<void>;
  loadMoreMessages: () => Promise<void>;
  clearError: () => void;
  startNewConversation: () => void;
}

interface SendMessageOptions {
  timeFilter?: string;
  includeGraphExpansion?: boolean;
  includeAggregates?: boolean;
  maxResults?: number;
}

const ConversationContext = createContext<ConversationContextType | null>(null);

export function useConversation() {
  const context = useContext(ConversationContext);
  if (!context) {
    throw new Error('useConversation must be used within a ConversationProvider');
  }
  return context;
}

interface ConversationProviderProps {
  children: ReactNode;
}

export function ConversationProvider({ children }: ConversationProviderProps) {
  const [state, setState] = useState<ConversationState>({
    conversations: [],
    currentConversationId: null,
    messagesByConversation: {},
    loading: false,
    error: null,
    hasMoreMessages: false,
    pendingConversations: new Set(),
  });

  const messageOffsetRef = useRef<Record<string, number>>({});
  const MESSAGE_LIMIT = 50;

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  // Computed values
  const currentConversation = state.conversations.find(
    c => c.conversation_id === state.currentConversationId
  ) || null;

  const messages = state.currentConversationId
    ? state.messagesByConversation[state.currentConversationId] || []
    : [];

  const sending = state.currentConversationId
    ? state.pendingConversations.has(state.currentConversationId)
    : false;

  const isConversationPending = useCallback((conversationId: string) => {
    return state.pendingConversations.has(conversationId);
  }, [state.pendingConversations]);

  const loadConversations = useCallback(async () => {
    try {
      setState(prev => ({ ...prev, loading: true, error: null }));
      const result = await window.traceAPI.conversations.list({ limit: 100 });
      setState(prev => ({
        ...prev,
        conversations: result.conversations,
        loading: false,
      }));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load conversations';
      setState(prev => ({ ...prev, loading: false, error: errorMessage }));
    }
  }, []);

  const createConversation = useCallback(async (title?: string): Promise<Conversation | null> => {
    try {
      setState(prev => ({ ...prev, loading: true, error: null }));
      const result = await window.traceAPI.conversations.create(title);
      const newConversation = result.conversation;

      setState(prev => ({
        ...prev,
        conversations: [newConversation, ...prev.conversations],
        currentConversationId: newConversation.conversation_id,
        messagesByConversation: {
          ...prev.messagesByConversation,
          [newConversation.conversation_id]: [],
        },
        loading: false,
        hasMoreMessages: false,
      }));
      messageOffsetRef.current[newConversation.conversation_id] = 0;

      return newConversation;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create conversation';
      setState(prev => ({ ...prev, loading: false, error: errorMessage }));
      return null;
    }
  }, []);

  const selectConversation = useCallback(async (conversationId: string) => {
    // If we already have messages cached, just switch to it
    if (state.messagesByConversation[conversationId]) {
      setState(prev => ({
        ...prev,
        currentConversationId: conversationId,
        error: null,
      }));
      return;
    }

    // Otherwise, load the conversation
    try {
      setState(prev => ({ ...prev, loading: true, error: null }));
      const result = await window.traceAPI.conversations.get(conversationId, {
        messageLimit: MESSAGE_LIMIT,
        messageOffset: 0,
      });

      setState(prev => ({
        ...prev,
        currentConversationId: conversationId,
        messagesByConversation: {
          ...prev.messagesByConversation,
          [conversationId]: result.messages,
        },
        loading: false,
        hasMoreMessages: result.has_more,
      }));
      messageOffsetRef.current[conversationId] = result.messages.length;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load conversation';
      setState(prev => ({ ...prev, loading: false, error: errorMessage }));
    }
  }, [state.messagesByConversation]);

  const sendMessage = useCallback(async (
    query: string,
    options?: SendMessageOptions
  ): Promise<ConversationSendResponse | null> => {
    // Capture the conversation ID at the start
    let conversationId = state.currentConversationId;

    // If no current conversation, create one first
    if (!conversationId) {
      const newConv = await createConversation();
      if (!newConv) return null;
      conversationId = newConv.conversation_id;
    }

    // Mark this conversation as pending
    setState(prev => ({
      ...prev,
      pendingConversations: new Set([...prev.pendingConversations, conversationId!]),
      error: null,
    }));

    try {
      const result = await window.traceAPI.conversations.send(conversationId, query, options);

      // Update state - always update conversation list, conditionally update messages
      setState(prev => {
        // Remove from pending
        const newPending = new Set(prev.pendingConversations);
        newPending.delete(conversationId!);

        // Update conversation metadata in the list
        const updatedConversations = prev.conversations.map(c =>
          c.conversation_id === conversationId
            ? {
                ...c,
                title: result.new_title || c.title,
                updated_ts: new Date().toISOString(),
                message_count: (c.message_count || 0) + 2,
                last_message_preview: result.assistant_message.content,
              }
            : c
        );

        // Move the updated conversation to the top (after pinned)
        const convIndex = updatedConversations.findIndex(c => c.conversation_id === conversationId);
        if (convIndex > 0) {
          const [conv] = updatedConversations.splice(convIndex, 1);
          // Find first non-pinned position
          const insertIndex = updatedConversations.findIndex(c => !c.pinned);
          if (insertIndex >= 0) {
            updatedConversations.splice(insertIndex, 0, conv);
          } else {
            updatedConversations.push(conv);
          }
        }

        // Update messages for this specific conversation
        const updatedMessages = {
          ...prev.messagesByConversation,
          [conversationId!]: [
            ...(prev.messagesByConversation[conversationId!] || []),
            result.user_message,
            result.assistant_message,
          ],
        };

        return {
          ...prev,
          conversations: updatedConversations,
          messagesByConversation: updatedMessages,
          pendingConversations: newPending,
        };
      });

      // Update offset
      messageOffsetRef.current[conversationId] = (messageOffsetRef.current[conversationId] || 0) + 2;

      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
      setState(prev => {
        const newPending = new Set(prev.pendingConversations);
        newPending.delete(conversationId!);
        return {
          ...prev,
          pendingConversations: newPending,
          error: errorMessage,
        };
      });
      return null;
    }
  }, [state.currentConversationId, createConversation]);

  const renameConversation = useCallback(async (conversationId: string, title: string) => {
    try {
      const result = await window.traceAPI.conversations.update(conversationId, { title });
      if (result.success) {
        setState(prev => ({
          ...prev,
          conversations: prev.conversations.map(c =>
            c.conversation_id === conversationId ? { ...c, title } : c
          ),
        }));
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to rename conversation';
      setState(prev => ({ ...prev, error: errorMessage }));
    }
  }, []);

  const deleteConversation = useCallback(async (conversationId: string) => {
    try {
      const result = await window.traceAPI.conversations.delete(conversationId);
      if (result.success) {
        setState(prev => {
          const newConversations = prev.conversations.filter(
            c => c.conversation_id !== conversationId
          );
          const needsNewSelection = prev.currentConversationId === conversationId;

          // Remove cached messages
          const newMessages = { ...prev.messagesByConversation };
          delete newMessages[conversationId];

          // Remove from pending
          const newPending = new Set(prev.pendingConversations);
          newPending.delete(conversationId);

          return {
            ...prev,
            conversations: newConversations,
            currentConversationId: needsNewSelection ? null : prev.currentConversationId,
            messagesByConversation: newMessages,
            pendingConversations: newPending,
          };
        });

        // Clean up offset
        delete messageOffsetRef.current[conversationId];
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete conversation';
      setState(prev => ({ ...prev, error: errorMessage }));
    }
  }, []);

  const togglePin = useCallback(async (conversationId: string) => {
    const conversation = state.conversations.find(c => c.conversation_id === conversationId);
    if (!conversation) return;

    try {
      const newPinned = !conversation.pinned;
      await window.traceAPI.conversations.update(conversationId, { pinned: newPinned });

      setState(prev => ({
        ...prev,
        conversations: prev.conversations.map(c =>
          c.conversation_id === conversationId ? { ...c, pinned: newPinned } : c
        ),
      }));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update conversation';
      setState(prev => ({ ...prev, error: errorMessage }));
    }
  }, [state.conversations]);

  const archiveConversation = useCallback(async (conversationId: string) => {
    try {
      await window.traceAPI.conversations.update(conversationId, { archived: true });

      setState(prev => {
        const newMessages = { ...prev.messagesByConversation };
        delete newMessages[conversationId];

        const newPending = new Set(prev.pendingConversations);
        newPending.delete(conversationId);

        return {
          ...prev,
          conversations: prev.conversations.filter(c => c.conversation_id !== conversationId),
          currentConversationId:
            prev.currentConversationId === conversationId
              ? null
              : prev.currentConversationId,
          messagesByConversation: newMessages,
          pendingConversations: newPending,
        };
      });

      delete messageOffsetRef.current[conversationId];
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to archive conversation';
      setState(prev => ({ ...prev, error: errorMessage }));
    }
  }, []);

  const loadMoreMessages = useCallback(async () => {
    const conversationId = state.currentConversationId;
    if (!conversationId || !state.hasMoreMessages || state.loading) return;

    const currentOffset = messageOffsetRef.current[conversationId] || 0;

    try {
      setState(prev => ({ ...prev, loading: true }));

      const result = await window.traceAPI.conversations.get(conversationId, {
        messageLimit: MESSAGE_LIMIT,
        messageOffset: currentOffset,
      });

      setState(prev => ({
        ...prev,
        messagesByConversation: {
          ...prev.messagesByConversation,
          [conversationId]: [
            ...result.messages,
            ...(prev.messagesByConversation[conversationId] || []),
          ],
        },
        loading: false,
        hasMoreMessages: result.has_more,
      }));

      messageOffsetRef.current[conversationId] = currentOffset + result.messages.length;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load more messages';
      setState(prev => ({ ...prev, loading: false, error: errorMessage }));
    }
  }, [state.currentConversationId, state.hasMoreMessages, state.loading]);

  const startNewConversation = useCallback(() => {
    setState(prev => ({
      ...prev,
      currentConversationId: null,
      hasMoreMessages: false,
    }));
  }, []);

  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
  }, []);

  const contextValue: ConversationContextType = {
    conversations: state.conversations,
    currentConversation,
    messages,
    loading: state.loading,
    sending,
    error: state.error,
    hasMoreMessages: state.hasMoreMessages,
    isConversationPending,
    loadConversations,
    createConversation,
    selectConversation,
    sendMessage,
    renameConversation,
    deleteConversation,
    togglePin,
    archiveConversation,
    loadMoreMessages,
    clearError,
    startNewConversation,
  };

  return (
    <ConversationContext.Provider value={contextValue}>
      {children}
    </ConversationContext.Provider>
  );
}

export default ConversationProvider;
