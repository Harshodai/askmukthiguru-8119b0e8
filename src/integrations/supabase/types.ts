export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      alert_events: {
        Row: {
          fired_at: string
          id: string
          message: string | null
          resolved_at: string | null
          rule_id: string | null
          rule_name: string | null
          value: number | null
        }
        Insert: {
          fired_at?: string
          id?: string
          message?: string | null
          resolved_at?: string | null
          rule_id?: string | null
          rule_name?: string | null
          value?: number | null
        }
        Update: {
          fired_at?: string
          id?: string
          message?: string | null
          resolved_at?: string | null
          rule_id?: string | null
          rule_name?: string | null
          value?: number | null
        }
        Relationships: []
      }
      alert_rules: {
        Row: {
          active: boolean
          channel: string
          comparator: string | null
          created_at: string
          enabled: boolean
          id: string
          metric: string
          name: string
          target: string
          threshold: number | null
          window_minutes: number
        }
        Insert: {
          active?: boolean
          channel?: string
          comparator?: string | null
          created_at?: string
          enabled?: boolean
          id?: string
          metric: string
          name: string
          target?: string
          threshold?: number | null
          window_minutes?: number
        }
        Update: {
          active?: boolean
          channel?: string
          comparator?: string | null
          created_at?: string
          enabled?: boolean
          id?: string
          metric?: string
          name?: string
          target?: string
          threshold?: number | null
          window_minutes?: number
        }
        Relationships: []
      }
      annotations: {
        Row: {
          author_id: string | null
          body: string
          created_at: string
          id: string
          label: string | null
          notes: string | null
          promoted_to_golden: boolean
          query_id: string | null
          response_id: string | null
        }
        Insert: {
          author_id?: string | null
          body: string
          created_at?: string
          id?: string
          label?: string | null
          notes?: string | null
          promoted_to_golden?: boolean
          query_id?: string | null
          response_id?: string | null
        }
        Update: {
          author_id?: string | null
          body?: string
          created_at?: string
          id?: string
          label?: string | null
          notes?: string | null
          promoted_to_golden?: boolean
          query_id?: string | null
          response_id?: string | null
        }
        Relationships: []
      }
      app_logs: {
        Row: {
          context: Json | null
          created_at: string
          id: string
          level: string
          message: string
          request_id: string
        }
        Insert: {
          context?: Json | null
          created_at?: string
          id?: string
          level?: string
          message: string
          request_id?: string
        }
        Update: {
          context?: Json | null
          created_at?: string
          id?: string
          level?: string
          message?: string
          request_id?: string
        }
        Relationships: []
      }
      app_settings: {
        Row: {
          key: string
          updated_at: string
          value: Json
        }
        Insert: {
          key: string
          updated_at?: string
          value: Json
        }
        Update: {
          key?: string
          updated_at?: string
          value?: Json
        }
        Relationships: []
      }
      assistant_access: {
        Row: {
          assistant_id: string
          created_at: string
          granted_via: string
          user_id: string
        }
        Insert: {
          assistant_id: string
          created_at?: string
          granted_via?: string
          user_id: string
        }
        Update: {
          assistant_id?: string
          created_at?: string
          granted_via?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "assistant_access_assistant_id_fkey"
            columns: ["assistant_id"]
            isOneToOne: false
            referencedRelation: "assistants"
            referencedColumns: ["id"]
          },
        ]
      }
      assistants: {
        Row: {
          avatar_url: string | null
          created_at: string
          created_by: string | null
          description: string
          id: string
          invite_code: string | null
          knowledge_tags: string[]
          name: string
          slug: string
          starter_questions: Json
          system_prompt: string
          updated_at: string
          visibility: Database["public"]["Enums"]["assistant_visibility"]
        }
        Insert: {
          avatar_url?: string | null
          created_at?: string
          created_by?: string | null
          description?: string
          id?: string
          invite_code?: string | null
          knowledge_tags?: string[]
          name: string
          slug: string
          starter_questions?: Json
          system_prompt?: string
          updated_at?: string
          visibility?: Database["public"]["Enums"]["assistant_visibility"]
        }
        Update: {
          avatar_url?: string | null
          created_at?: string
          created_by?: string | null
          description?: string
          id?: string
          invite_code?: string | null
          knowledge_tags?: string[]
          name?: string
          slug?: string
          starter_questions?: Json
          system_prompt?: string
          updated_at?: string
          visibility?: Database["public"]["Enums"]["assistant_visibility"]
        }
        Relationships: []
      }
      chat_messages: {
        Row: {
          citations: string[] | null
          confidence_score: number | null
          content: string
          conversation_id: string
          created_at: string
          id: string
          role: string
        }
        Insert: {
          citations?: string[] | null
          confidence_score?: number | null
          content: string
          conversation_id: string
          created_at?: string
          id?: string
          role: string
        }
        Update: {
          citations?: string[] | null
          confidence_score?: number | null
          content?: string
          conversation_id?: string
          created_at?: string
          id?: string
          role?: string
        }
        Relationships: [
          {
            foreignKeyName: "chat_messages_conversation_id_fkey"
            columns: ["conversation_id"]
            isOneToOne: false
            referencedRelation: "conversations"
            referencedColumns: ["id"]
          },
        ]
      }
      chat_queries: {
        Row: {
          completion_tokens: number | null
          cost_estimate: number | null
          created_at: string
          id: string
          latency_ms: number | null
          model: string | null
          prompt_tokens: number | null
          prompt_version_id: string | null
          query_text: string
          status: string
          user_id: string | null
        }
        Insert: {
          completion_tokens?: number | null
          cost_estimate?: number | null
          created_at?: string
          id?: string
          latency_ms?: number | null
          model?: string | null
          prompt_tokens?: number | null
          prompt_version_id?: string | null
          query_text: string
          status?: string
          user_id?: string | null
        }
        Update: {
          completion_tokens?: number | null
          cost_estimate?: number | null
          created_at?: string
          id?: string
          latency_ms?: number | null
          model?: string | null
          prompt_tokens?: number | null
          prompt_version_id?: string | null
          query_text?: string
          status?: string
          user_id?: string | null
        }
        Relationships: []
      }
      chat_responses: {
        Row: {
          answer_relevancy: number | null
          citations: Json | null
          confidence: number | null
          context_precision: number | null
          context_recall: number | null
          created_at: string
          faithfulness: number | null
          hallucination_flag: boolean | null
          id: string
          judge_reasoning: string | null
          query_id: string
          response_text: string | null
        }
        Insert: {
          answer_relevancy?: number | null
          citations?: Json | null
          confidence?: number | null
          context_precision?: number | null
          context_recall?: number | null
          created_at?: string
          faithfulness?: number | null
          hallucination_flag?: boolean | null
          id?: string
          judge_reasoning?: string | null
          query_id: string
          response_text?: string | null
        }
        Update: {
          answer_relevancy?: number | null
          citations?: Json | null
          confidence?: number | null
          context_precision?: number | null
          context_recall?: number | null
          created_at?: string
          faithfulness?: number | null
          hallucination_flag?: boolean | null
          id?: string
          judge_reasoning?: string | null
          query_id?: string
          response_text?: string | null
        }
        Relationships: []
      }
      chat_sessions: {
        Row: {
          created_at: string
          id: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          user_id?: string
        }
        Relationships: []
      }
      conversations: {
        Row: {
          assistant_id: string | null
          created_at: string
          id: string
          preview: string | null
          title: string | null
          updated_at: string
          user_id: string
        }
        Insert: {
          assistant_id?: string | null
          created_at?: string
          id?: string
          preview?: string | null
          title?: string | null
          updated_at?: string
          user_id: string
        }
        Update: {
          assistant_id?: string | null
          created_at?: string
          id?: string
          preview?: string | null
          title?: string | null
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "conversations_assistant_id_fkey"
            columns: ["assistant_id"]
            isOneToOne: false
            referencedRelation: "assistants"
            referencedColumns: ["id"]
          },
        ]
      }
      daily_teachings: {
        Row: {
          caption: string | null
          created_at: string | null
          created_by: string | null
          expires_at: string | null
          id: string
          image_url: string
        }
        Insert: {
          caption?: string | null
          created_at?: string | null
          created_by?: string | null
          expires_at?: string | null
          id?: string
          image_url: string
        }
        Update: {
          caption?: string | null
          created_at?: string | null
          created_by?: string | null
          expires_at?: string | null
          id?: string
          image_url?: string
        }
        Relationships: []
      }
      eval_results: {
        Row: {
          answer: string | null
          created_at: string
          id: string
          metrics: Json | null
          question: string | null
          run_id: string | null
          score: number | null
        }
        Insert: {
          answer?: string | null
          created_at?: string
          id?: string
          metrics?: Json | null
          question?: string | null
          run_id?: string | null
          score?: number | null
        }
        Update: {
          answer?: string | null
          created_at?: string
          id?: string
          metrics?: Json | null
          question?: string | null
          run_id?: string | null
          score?: number | null
        }
        Relationships: []
      }
      eval_runs: {
        Row: {
          finished_at: string | null
          id: string
          name: string
          prompt_version_id: string | null
          started_at: string
          status: string
          summary: Json | null
          triggered_by: string
        }
        Insert: {
          finished_at?: string | null
          id?: string
          name: string
          prompt_version_id?: string | null
          started_at?: string
          status?: string
          summary?: Json | null
          triggered_by?: string
        }
        Update: {
          finished_at?: string | null
          id?: string
          name?: string
          prompt_version_id?: string | null
          started_at?: string
          status?: string
          summary?: Json | null
          triggered_by?: string
        }
        Relationships: []
      }
      feedback_events: {
        Row: {
          comment: string | null
          created_at: string
          id: string
          query_id: string | null
          rating: number
          user_id: string | null
        }
        Insert: {
          comment?: string | null
          created_at?: string
          id?: string
          query_id?: string | null
          rating?: number
          user_id?: string | null
        }
        Update: {
          comment?: string | null
          created_at?: string
          id?: string
          query_id?: string | null
          rating?: number
          user_id?: string | null
        }
        Relationships: []
      }
      golden_questions: {
        Row: {
          active: boolean
          created_at: string
          expected_answer: string | null
          expected_sources: string[]
          id: string
          question: string
          tags: string[] | null
        }
        Insert: {
          active?: boolean
          created_at?: string
          expected_answer?: string | null
          expected_sources?: string[]
          id?: string
          question: string
          tags?: string[] | null
        }
        Update: {
          active?: boolean
          created_at?: string
          expected_answer?: string | null
          expected_sources?: string[]
          id?: string
          question?: string
          tags?: string[] | null
        }
        Relationships: []
      }
      guru_core_memory: {
        Row: {
          content: string
          created_at: string
          id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          content?: string
          created_at?: string
          id?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          content?: string
          created_at?: string
          id?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      guru_memories: {
        Row: {
          claim: string | null
          confidence: number | null
          content: string
          created_at: string
          decay_score: number | null
          embedding: string | null
          id: string
          source: string
          updated_at: string
          user_id: string
        }
        Insert: {
          claim?: string | null
          confidence?: number | null
          content: string
          created_at?: string
          decay_score?: number | null
          embedding?: string | null
          id?: string
          source?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          claim?: string | null
          confidence?: number | null
          content?: string
          created_at?: string
          decay_score?: number | null
          embedding?: string | null
          id?: string
          source?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      guru_session_summaries: {
        Row: {
          created_at: string
          id: string
          session_id: string
          summary: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          session_id: string
          summary: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          session_id?: string
          summary?: string
          user_id?: string
        }
        Relationships: []
      }
      ingestion_runs: {
        Row: {
          chunks_added: number | null
          created_at: string
          details: Json | null
          duration_ms: number
          error_log: string | null
          id: string
          source: string
          status: string
        }
        Insert: {
          chunks_added?: number | null
          created_at?: string
          details?: Json | null
          duration_ms?: number
          error_log?: string | null
          id?: string
          source: string
          status?: string
        }
        Update: {
          chunks_added?: number | null
          created_at?: string
          details?: Json | null
          duration_ms?: number
          error_log?: string | null
          id?: string
          source?: string
          status?: string
        }
        Relationships: []
      }
      kb_chunks: {
        Row: {
          created_at: string
          embedding: string | null
          id: string
          ord: number
          source_id: string
          text: string
          token_count: number | null
        }
        Insert: {
          created_at?: string
          embedding?: string | null
          id?: string
          ord?: number
          source_id: string
          text: string
          token_count?: number | null
        }
        Update: {
          created_at?: string
          embedding?: string | null
          id?: string
          ord?: number
          source_id?: string
          text?: string
          token_count?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "kb_chunks_source_id_fkey"
            columns: ["source_id"]
            isOneToOne: false
            referencedRelation: "kb_sources"
            referencedColumns: ["id"]
          },
        ]
      }
      kb_sources: {
        Row: {
          chunk_count: number
          created_at: string
          created_by: string | null
          id: string
          kind: string
          metadata: Json
          status: string
          title: string
          updated_at: string
          url: string | null
        }
        Insert: {
          chunk_count?: number
          created_at?: string
          created_by?: string | null
          id?: string
          kind?: string
          metadata?: Json
          status?: string
          title: string
          updated_at?: string
          url?: string | null
        }
        Update: {
          chunk_count?: number
          created_at?: string
          created_by?: string | null
          id?: string
          kind?: string
          metadata?: Json
          status?: string
          title?: string
          updated_at?: string
          url?: string | null
        }
        Relationships: []
      }
      meditation_sessions: {
        Row: {
          breath_cycles: number | null
          completed: boolean | null
          completed_at: string | null
          created_at: string | null
          duration_seconds: number | null
          id: string
          started_at: string
          user_id: string
        }
        Insert: {
          breath_cycles?: number | null
          completed?: boolean | null
          completed_at?: string | null
          created_at?: string | null
          duration_seconds?: number | null
          id?: string
          started_at?: string
          user_id: string
        }
        Update: {
          breath_cycles?: number | null
          completed?: boolean | null
          completed_at?: string | null
          created_at?: string | null
          duration_seconds?: number | null
          id?: string
          started_at?: string
          user_id?: string
        }
        Relationships: []
      }
      model_pricing: {
        Row: {
          id: string
          input_per_1k: number
          model: string
          output_per_1k: number
          updated_at: string
        }
        Insert: {
          id?: string
          input_per_1k?: number
          model: string
          output_per_1k?: number
          updated_at?: string
        }
        Update: {
          id?: string
          input_per_1k?: number
          model?: string
          output_per_1k?: number
          updated_at?: string
        }
        Relationships: []
      }
      notes: {
        Row: {
          body: string
          created_at: string
          id: string
          is_favorite: boolean
          source_conversation_id: string | null
          source_message_id: string | null
          tags: string[]
          title: string
          updated_at: string
          user_id: string
        }
        Insert: {
          body?: string
          created_at?: string
          id?: string
          is_favorite?: boolean
          source_conversation_id?: string | null
          source_message_id?: string | null
          tags?: string[]
          title?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          body?: string
          created_at?: string
          id?: string
          is_favorite?: boolean
          source_conversation_id?: string | null
          source_message_id?: string | null
          tags?: string[]
          title?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      pending_extractions: {
        Row: {
          attempts: number
          created_at: string
          id: string
          last_error: string | null
          payload: Json
          processed_at: string | null
          status: string
          user_id: string
        }
        Insert: {
          attempts?: number
          created_at?: string
          id?: string
          last_error?: string | null
          payload: Json
          processed_at?: string | null
          status?: string
          user_id: string
        }
        Update: {
          attempts?: number
          created_at?: string
          id?: string
          last_error?: string | null
          payload?: Json
          processed_at?: string | null
          status?: string
          user_id?: string
        }
        Relationships: []
      }
      profiles: {
        Row: {
          avatar_url: string | null
          created_at: string | null
          display_name: string | null
          id: string
          last_active_at: string | null
          last_conversation_id: string | null
          last_device_id: string | null
          last_message_id: string | null
          preferred_language: string | null
          tts_enabled: boolean | null
        }
        Insert: {
          avatar_url?: string | null
          created_at?: string | null
          display_name?: string | null
          id: string
          last_active_at?: string | null
          last_conversation_id?: string | null
          last_device_id?: string | null
          last_message_id?: string | null
          preferred_language?: string | null
          tts_enabled?: boolean | null
        }
        Update: {
          avatar_url?: string | null
          created_at?: string | null
          display_name?: string | null
          id?: string
          last_active_at?: string | null
          last_conversation_id?: string | null
          last_device_id?: string | null
          last_message_id?: string | null
          preferred_language?: string | null
          tts_enabled?: boolean | null
        }
        Relationships: []
      }
      prompt_versions: {
        Row: {
          active: boolean
          author: string | null
          body: string | null
          created_at: string
          description: string | null
          id: string
          name: string
          version: string
        }
        Insert: {
          active?: boolean
          author?: string | null
          body?: string | null
          created_at?: string
          description?: string | null
          id?: string
          name: string
          version?: string
        }
        Update: {
          active?: boolean
          author?: string | null
          body?: string | null
          created_at?: string
          description?: string | null
          id?: string
          name?: string
          version?: string
        }
        Relationships: []
      }
      push_subscriptions: {
        Row: {
          auth: string
          created_at: string
          device_label: string | null
          endpoint: string
          id: string
          last_seen_at: string
          p256dh: string
          user_agent: string | null
          user_id: string
        }
        Insert: {
          auth: string
          created_at?: string
          device_label?: string | null
          endpoint: string
          id?: string
          last_seen_at?: string
          p256dh: string
          user_agent?: string | null
          user_id: string
        }
        Update: {
          auth?: string
          created_at?: string
          device_label?: string | null
          endpoint?: string
          id?: string
          last_seen_at?: string
          p256dh?: string
          user_agent?: string | null
          user_id?: string
        }
        Relationships: []
      }
      query_clusters: {
        Row: {
          centroid: Json | null
          created_at: string
          id: string
          label: string
          size: number
        }
        Insert: {
          centroid?: Json | null
          created_at?: string
          id?: string
          label: string
          size?: number
        }
        Update: {
          centroid?: Json | null
          created_at?: string
          id?: string
          label?: string
          size?: number
        }
        Relationships: []
      }
      retrieval_events: {
        Row: {
          created_at: string
          id: string
          query_id: string
          scores: number[] | null
          source_docs: string[] | null
        }
        Insert: {
          created_at?: string
          id?: string
          query_id: string
          scores?: number[] | null
          source_docs?: string[] | null
        }
        Update: {
          created_at?: string
          id?: string
          query_id?: string
          scores?: number[] | null
          source_docs?: string[] | null
        }
        Relationships: []
      }
      safety_events: {
        Row: {
          action: string | null
          created_at: string
          details: Json | null
          excerpt: string | null
          id: string
          query_id: string | null
          rule: string
          severity: string | null
          type: string | null
        }
        Insert: {
          action?: string | null
          created_at?: string
          details?: Json | null
          excerpt?: string | null
          id?: string
          query_id?: string | null
          rule: string
          severity?: string | null
          type?: string | null
        }
        Update: {
          action?: string | null
          created_at?: string
          details?: Json | null
          excerpt?: string | null
          id?: string
          query_id?: string | null
          rule?: string
          severity?: string | null
          type?: string | null
        }
        Relationships: []
      }
      telemetry_events: {
        Row: {
          created_at: string
          id: string
          last_message_id: string | null
          metric_type: string
          metric_value: number
          session_id: string | null
          tags: Json | null
          user_id: string | null
          user_message_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          last_message_id?: string | null
          metric_type: string
          metric_value: number
          session_id?: string | null
          tags?: Json | null
          user_id?: string | null
          user_message_id: string
        }
        Update: {
          created_at?: string
          id?: string
          last_message_id?: string | null
          metric_type?: string
          metric_value?: number
          session_id?: string | null
          tags?: Json | null
          user_id?: string | null
          user_message_id?: string
        }
        Relationships: []
      }
      trace_spans: {
        Row: {
          created_at: string
          duration_ms: number
          id: string
          query_id: string
          span_name: string
          start_ms: number
        }
        Insert: {
          created_at?: string
          duration_ms?: number
          id?: string
          query_id: string
          span_name: string
          start_ms?: number
        }
        Update: {
          created_at?: string
          duration_ms?: number
          id?: string
          query_id?: string
          span_name?: string
          start_ms?: number
        }
        Relationships: []
      }
      trigger_events: {
        Row: {
          created_at: string
          id: string
          payload: Json | null
          query_id: string | null
          trigger_name: string | null
          trigger_type: string
        }
        Insert: {
          created_at?: string
          id?: string
          payload?: Json | null
          query_id?: string | null
          trigger_name?: string | null
          trigger_type: string
        }
        Update: {
          created_at?: string
          id?: string
          payload?: Json | null
          query_id?: string | null
          trigger_name?: string | null
          trigger_type?: string
        }
        Relationships: []
      }
      user_profiles: {
        Row: {
          first_seen: string
          id: string
          last_seen: string
          total_queries: number
          user_id: string
        }
        Insert: {
          first_seen?: string
          id?: string
          last_seen?: string
          total_queries?: number
          user_id: string
        }
        Update: {
          first_seen?: string
          id?: string
          last_seen?: string
          total_queries?: number
          user_id?: string
        }
        Relationships: []
      }
      user_roles: {
        Row: {
          id: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Insert: {
          id?: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Update: {
          id?: string
          role?: Database["public"]["Enums"]["app_role"]
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      demote_admin_by_id: { Args: { _user_id: string }; Returns: Json }
      ensure_profile_and_role: { Args: never; Returns: Json }
      has_role: {
        Args: {
          _role: Database["public"]["Enums"]["app_role"]
          _user_id: string
        }
        Returns: boolean
      }
      list_admins: {
        Args: never
        Returns: {
          created_at: string
          email: string
          id: string
        }[]
      }
      match_user_memories: {
        Args: { p_k: number; p_min_sim: number; p_query_embedding: string }
        Returns: {
          content: string
          id: string
          similarity: number
        }[]
      }
      promote_admin_by_email: { Args: { _email: string }; Returns: Json }
      seed_admin_demo: { Args: never; Returns: Json }
      whoami_diagnostics: { Args: never; Returns: Json }
    }
    Enums: {
      app_role: "admin" | "user"
      assistant_visibility: "public" | "link" | "private"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      app_role: ["admin", "user"],
      assistant_visibility: ["public", "link", "private"],
    },
  },
} as const
