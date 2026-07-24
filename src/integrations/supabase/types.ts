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
          fired_at: string | null
          id: string
          resolved_at: string | null
          rule_id: string | null
          rule_name: string | null
          value: number | null
        }
        Insert: {
          fired_at?: string | null
          id?: string
          resolved_at?: string | null
          rule_id?: string | null
          rule_name?: string | null
          value?: number | null
        }
        Update: {
          fired_at?: string | null
          id?: string
          resolved_at?: string | null
          rule_id?: string | null
          rule_name?: string | null
          value?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "alert_events_rule_id_fkey"
            columns: ["rule_id"]
            isOneToOne: false
            referencedRelation: "alert_rules"
            referencedColumns: ["id"]
          },
        ]
      }
      alert_rules: {
        Row: {
          active: boolean | null
          channel: string | null
          comparator: string | null
          id: string
          metric: string | null
          name: string | null
          target: string | null
          threshold: number | null
          window_minutes: number | null
        }
        Insert: {
          active?: boolean | null
          channel?: string | null
          comparator?: string | null
          id?: string
          metric?: string | null
          name?: string | null
          target?: string | null
          threshold?: number | null
          window_minutes?: number | null
        }
        Update: {
          active?: boolean | null
          channel?: string | null
          comparator?: string | null
          id?: string
          metric?: string | null
          name?: string | null
          target?: string | null
          threshold?: number | null
          window_minutes?: number | null
        }
        Relationships: []
      }
      annotations: {
        Row: {
          created_at: string | null
          id: string
          label: string | null
          notes: string | null
          promoted_to_golden: boolean | null
          response_id: string | null
          reviewer_id: string | null
        }
        Insert: {
          created_at?: string | null
          id?: string
          label?: string | null
          notes?: string | null
          promoted_to_golden?: boolean | null
          response_id?: string | null
          reviewer_id?: string | null
        }
        Update: {
          created_at?: string | null
          id?: string
          label?: string | null
          notes?: string | null
          promoted_to_golden?: boolean | null
          response_id?: string | null
          reviewer_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "annotations_response_id_fkey"
            columns: ["response_id"]
            isOneToOne: false
            referencedRelation: "chat_responses"
            referencedColumns: ["id"]
          },
        ]
      }
      app_logs: {
        Row: {
          context: Json | null
          created_at: string | null
          id: number
          level: string | null
          message: string | null
          request_id: string | null
        }
        Insert: {
          context?: Json | null
          created_at?: string | null
          id?: number
          level?: string | null
          message?: string | null
          request_id?: string | null
        }
        Update: {
          context?: Json | null
          created_at?: string | null
          id?: number
          level?: string | null
          message?: string | null
          request_id?: string | null
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
      assistant_configurations: {
        Row: {
          created_at: string | null
          guru_id: string | null
          id: string
          is_default: boolean | null
          knowledge_tags: string[] | null
          name: string
          slug: string
          system_prompt: string | null
        }
        Insert: {
          created_at?: string | null
          guru_id?: string | null
          id?: string
          is_default?: boolean | null
          knowledge_tags?: string[] | null
          name: string
          slug: string
          system_prompt?: string | null
        }
        Update: {
          created_at?: string | null
          guru_id?: string | null
          id?: string
          is_default?: boolean | null
          knowledge_tags?: string[] | null
          name?: string
          slug?: string
          system_prompt?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "assistant_configurations_guru_id_fkey"
            columns: ["guru_id"]
            isOneToOne: false
            referencedRelation: "gurus"
            referencedColumns: ["id"]
          },
        ]
      }
      assistant_doctrines: {
        Row: {
          assistant_slug: string
          canonical_terms: string[] | null
          created_at: string | null
          id: string
          synonyms_json: Json | null
        }
        Insert: {
          assistant_slug: string
          canonical_terms?: string[] | null
          created_at?: string | null
          id?: string
          synonyms_json?: Json | null
        }
        Update: {
          assistant_slug?: string
          canonical_terms?: string[] | null
          created_at?: string | null
          id?: string
          synonyms_json?: Json | null
        }
        Relationships: []
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
      cancellations: {
        Row: {
          completed_deletion: string | null
          created_at: string | null
          data_retention: string | null
          id: string
          reactivated_at: string | null
          reason: string | null
          scheduled_deletion: string | null
          status: string
          user_id: string | null
          win_back_emails_sent: Json | null
        }
        Insert: {
          completed_deletion?: string | null
          created_at?: string | null
          data_retention?: string | null
          id?: string
          reactivated_at?: string | null
          reason?: string | null
          scheduled_deletion?: string | null
          status: string
          user_id?: string | null
          win_back_emails_sent?: Json | null
        }
        Update: {
          completed_deletion?: string | null
          created_at?: string | null
          data_retention?: string | null
          id?: string
          reactivated_at?: string | null
          reason?: string | null
          scheduled_deletion?: string | null
          status?: string
          user_id?: string | null
          win_back_emails_sent?: Json | null
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
          anon_user_id: string | null
          assistant_slug: string | null
          cache_hit: boolean | null
          completion_tokens: number | null
          cost_estimate: number | null
          created_at: string | null
          id: string
          latency_ms: number | null
          model: string | null
          prompt_tokens: number | null
          prompt_version_id: string | null
          provider: string | null
          query_text: string
          route_decision: string | null
          session_id: string | null
          status: string | null
          tenant_id: string
          tokens_per_second: number | null
          ttft_ms: number | null
          user_id: string | null
        }
        Insert: {
          anon_user_id?: string | null
          assistant_slug?: string | null
          cache_hit?: boolean | null
          completion_tokens?: number | null
          cost_estimate?: number | null
          created_at?: string | null
          id?: string
          latency_ms?: number | null
          model?: string | null
          prompt_tokens?: number | null
          prompt_version_id?: string | null
          provider?: string | null
          query_text: string
          route_decision?: string | null
          session_id?: string | null
          status?: string | null
          tenant_id?: string
          tokens_per_second?: number | null
          ttft_ms?: number | null
          user_id?: string | null
        }
        Update: {
          anon_user_id?: string | null
          assistant_slug?: string | null
          cache_hit?: boolean | null
          completion_tokens?: number | null
          cost_estimate?: number | null
          created_at?: string | null
          id?: string
          latency_ms?: number | null
          model?: string | null
          prompt_tokens?: number | null
          prompt_version_id?: string | null
          provider?: string | null
          query_text?: string
          route_decision?: string | null
          session_id?: string | null
          status?: string | null
          tenant_id?: string
          tokens_per_second?: number | null
          ttft_ms?: number | null
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "chat_queries_prompt_version_id_fkey"
            columns: ["prompt_version_id"]
            isOneToOne: false
            referencedRelation: "prompt_versions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "chat_queries_session_id_fkey"
            columns: ["session_id"]
            isOneToOne: false
            referencedRelation: "chat_sessions"
            referencedColumns: ["id"]
          },
        ]
      }
      chat_responses: {
        Row: {
          answer_relevancy: number | null
          citations: Json | null
          citations_verified: boolean | null
          confidence: number | null
          context_precision: number | null
          context_recall: number | null
          created_at: string | null
          evaluation_trace: Json | null
          faithfulness: number | null
          hallucination_flag: boolean | null
          id: string
          judge_reasoning: string | null
          orphan_citations_stripped: boolean | null
          query_id: string | null
          response_text: string | null
          tenant_id: string
        }
        Insert: {
          answer_relevancy?: number | null
          citations?: Json | null
          citations_verified?: boolean | null
          confidence?: number | null
          context_precision?: number | null
          context_recall?: number | null
          created_at?: string | null
          evaluation_trace?: Json | null
          faithfulness?: number | null
          hallucination_flag?: boolean | null
          id?: string
          judge_reasoning?: string | null
          orphan_citations_stripped?: boolean | null
          query_id?: string | null
          response_text?: string | null
          tenant_id?: string
        }
        Update: {
          answer_relevancy?: number | null
          citations?: Json | null
          citations_verified?: boolean | null
          confidence?: number | null
          context_precision?: number | null
          context_recall?: number | null
          created_at?: string | null
          evaluation_trace?: Json | null
          faithfulness?: number | null
          hallucination_flag?: boolean | null
          id?: string
          judge_reasoning?: string | null
          orphan_citations_stripped?: boolean | null
          query_id?: string | null
          response_text?: string | null
          tenant_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "chat_responses_query_id_fkey"
            columns: ["query_id"]
            isOneToOne: false
            referencedRelation: "chat_queries"
            referencedColumns: ["id"]
          },
        ]
      }
      chat_sessions: {
        Row: {
          anon_user_id: string | null
          channel: string | null
          created_at: string
          id: string
          started_at: string | null
          user_id: string | null
        }
        Insert: {
          anon_user_id?: string | null
          channel?: string | null
          created_at?: string
          id?: string
          started_at?: string | null
          user_id?: string | null
        }
        Update: {
          anon_user_id?: string | null
          channel?: string | null
          created_at?: string
          id?: string
          started_at?: string | null
          user_id?: string | null
        }
        Relationships: []
      }
      conversation_memories: {
        Row: {
          emotional_arc: Json | null
          follow_up_suggestions: string[] | null
          key_insights: string[] | null
          messages: Json | null
          session_id: string
          started_at: number
          user_id: string | null
        }
        Insert: {
          emotional_arc?: Json | null
          follow_up_suggestions?: string[] | null
          key_insights?: string[] | null
          messages?: Json | null
          session_id: string
          started_at: number
          user_id?: string | null
        }
        Update: {
          emotional_arc?: Json | null
          follow_up_suggestions?: string[] | null
          key_insights?: string[] | null
          messages?: Json | null
          session_id?: string
          started_at?: number
          user_id?: string | null
        }
        Relationships: []
      }
      conversations: {
        Row: {
          assistant_id: string | null
          created_at: string
          id: string
          preview: string | null
          retention_days: number
          title: string | null
          updated_at: string
          user_id: string
        }
        Insert: {
          assistant_id?: string | null
          created_at?: string
          id?: string
          preview?: string | null
          retention_days?: number
          title?: string | null
          updated_at?: string
          user_id: string
        }
        Update: {
          assistant_id?: string | null
          created_at?: string
          id?: string
          preview?: string | null
          retention_days?: number
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
          answer_relevancy: number | null
          context_precision: number | null
          context_recall: number | null
          eval_run_id: string | null
          faithfulness: number | null
          golden_id: string | null
          id: string
          passed: boolean | null
          response_text: string | null
        }
        Insert: {
          answer_relevancy?: number | null
          context_precision?: number | null
          context_recall?: number | null
          eval_run_id?: string | null
          faithfulness?: number | null
          golden_id?: string | null
          id?: string
          passed?: boolean | null
          response_text?: string | null
        }
        Update: {
          answer_relevancy?: number | null
          context_precision?: number | null
          context_recall?: number | null
          eval_run_id?: string | null
          faithfulness?: number | null
          golden_id?: string | null
          id?: string
          passed?: boolean | null
          response_text?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "eval_results_eval_run_id_fkey"
            columns: ["eval_run_id"]
            isOneToOne: false
            referencedRelation: "eval_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "eval_results_golden_id_fkey"
            columns: ["golden_id"]
            isOneToOne: false
            referencedRelation: "golden_questions"
            referencedColumns: ["id"]
          },
        ]
      }
      eval_runs: {
        Row: {
          finished_at: string | null
          id: string
          prompt_version_id: string | null
          started_at: string | null
          summary: Json | null
          triggered_by: string | null
        }
        Insert: {
          finished_at?: string | null
          id?: string
          prompt_version_id?: string | null
          started_at?: string | null
          summary?: Json | null
          triggered_by?: string | null
        }
        Update: {
          finished_at?: string | null
          id?: string
          prompt_version_id?: string | null
          started_at?: string | null
          summary?: Json | null
          triggered_by?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "eval_runs_prompt_version_id_fkey"
            columns: ["prompt_version_id"]
            isOneToOne: false
            referencedRelation: "prompt_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      exit_surveys: {
        Row: {
          created_at: string | null
          details: string | null
          id: string
          reason: string
          responded_to: boolean | null
          response_type: string | null
          user_id: string | null
        }
        Insert: {
          created_at?: string | null
          details?: string | null
          id?: string
          reason: string
          responded_to?: boolean | null
          response_type?: string | null
          user_id?: string | null
        }
        Update: {
          created_at?: string | null
          details?: string | null
          id?: string
          reason?: string
          responded_to?: boolean | null
          response_type?: string | null
          user_id?: string | null
        }
        Relationships: []
      }
      feedback_events: {
        Row: {
          answer_text: string | null
          comment: string | null
          created_at: string
          feedback_text: string | null
          id: string
          metadata_json: Json | null
          query_id: string | null
          query_text: string | null
          rating: number
          user_id: string | null
        }
        Insert: {
          answer_text?: string | null
          comment?: string | null
          created_at?: string
          feedback_text?: string | null
          id?: string
          metadata_json?: Json | null
          query_id?: string | null
          query_text?: string | null
          rating?: number
          user_id?: string | null
        }
        Update: {
          answer_text?: string | null
          comment?: string | null
          created_at?: string
          feedback_text?: string | null
          id?: string
          metadata_json?: Json | null
          query_id?: string | null
          query_text?: string | null
          rating?: number
          user_id?: string | null
        }
        Relationships: []
      }
      golden_questions: {
        Row: {
          active: boolean | null
          expected_answer: string | null
          expected_sources: string[] | null
          id: string
          question: string | null
          tags: string[] | null
        }
        Insert: {
          active?: boolean | null
          expected_answer?: string | null
          expected_sources?: string[] | null
          id?: string
          question?: string | null
          tags?: string[] | null
        }
        Update: {
          active?: boolean | null
          expected_answer?: string | null
          expected_sources?: string[] | null
          id?: string
          question?: string | null
          tags?: string[] | null
        }
        Relationships: []
      }
      guru_core_memory: {
        Row: {
          content: string
          created_at: string
          id: string
          tenant_id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          content: string
          created_at?: string
          id?: string
          tenant_id?: string
          updated_at?: string
          user_id?: string
        }
        Update: {
          content?: string
          created_at?: string
          id?: string
          tenant_id?: string
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
          embedding: string
          id: string
          source: string
          summary: string | null
          tenant_id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          claim?: string | null
          confidence?: number | null
          content: string
          created_at?: string
          decay_score?: number | null
          embedding: string
          id?: string
          source?: string
          summary?: string | null
          tenant_id?: string
          updated_at?: string
          user_id?: string
        }
        Update: {
          claim?: string | null
          confidence?: number | null
          content?: string
          created_at?: string
          decay_score?: number | null
          embedding?: string
          id?: string
          source?: string
          summary?: string | null
          tenant_id?: string
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
          tenant_id: string
          updated_at: string
          user_id: string | null
        }
        Insert: {
          created_at?: string
          id?: string
          session_id: string
          summary: string
          tenant_id?: string
          updated_at?: string
          user_id?: string | null
        }
        Update: {
          created_at?: string
          id?: string
          session_id?: string
          summary?: string
          tenant_id?: string
          updated_at?: string
          user_id?: string | null
        }
        Relationships: []
      }
      gurus: {
        Row: {
          avatar_url: string | null
          collection_name: string
          created_at: string | null
          description: string | null
          id: string
          is_active: boolean | null
          name: string
          slug: string
        }
        Insert: {
          avatar_url?: string | null
          collection_name: string
          created_at?: string | null
          description?: string | null
          id?: string
          is_active?: boolean | null
          name: string
          slug: string
        }
        Update: {
          avatar_url?: string | null
          collection_name?: string
          created_at?: string | null
          description?: string | null
          id?: string
          is_active?: boolean | null
          name?: string
          slug?: string
        }
        Relationships: []
      }
      ingest_jobs: {
        Row: {
          chunks_indexed: number | null
          completed_at: string | null
          created_at: string | null
          error_message: string | null
          id: string
          progress_pct: number | null
          source_type: string | null
          source_url: string
          started_at: string | null
          status: string | null
          worker_id: string | null
        }
        Insert: {
          chunks_indexed?: number | null
          completed_at?: string | null
          created_at?: string | null
          error_message?: string | null
          id?: string
          progress_pct?: number | null
          source_type?: string | null
          source_url: string
          started_at?: string | null
          status?: string | null
          worker_id?: string | null
        }
        Update: {
          chunks_indexed?: number | null
          completed_at?: string | null
          created_at?: string | null
          error_message?: string | null
          id?: string
          progress_pct?: number | null
          source_type?: string | null
          source_url?: string
          started_at?: string | null
          status?: string | null
          worker_id?: string | null
        }
        Relationships: []
      }
      ingestion_checkpoints: {
        Row: {
          chunk_id: string
          created_at: string | null
          metadata: Json | null
          tenant_id: string
        }
        Insert: {
          chunk_id: string
          created_at?: string | null
          metadata?: Json | null
          tenant_id?: string
        }
        Update: {
          chunk_id?: string
          created_at?: string | null
          metadata?: Json | null
          tenant_id?: string
        }
        Relationships: []
      }
      ingestion_runs: {
        Row: {
          chunks_added: number | null
          created_at: string | null
          duration_ms: number | null
          embedding_model: string | null
          error_log: string | null
          id: string
          source: string | null
          status: string | null
        }
        Insert: {
          chunks_added?: number | null
          created_at?: string | null
          duration_ms?: number | null
          embedding_model?: string | null
          error_log?: string | null
          id?: string
          source?: string | null
          status?: string | null
        }
        Update: {
          chunks_added?: number | null
          created_at?: string | null
          duration_ms?: number | null
          embedding_model?: string | null
          error_log?: string | null
          id?: string
          source?: string | null
          status?: string | null
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
          currency: string | null
          input_per_1k: number | null
          model: string
          output_per_1k: number | null
        }
        Insert: {
          currency?: string | null
          input_per_1k?: number | null
          model: string
          output_per_1k?: number | null
        }
        Update: {
          currency?: string | null
          input_per_1k?: number | null
          model?: string
          output_per_1k?: number | null
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
      okf_review_queue: {
        Row: {
          entry_json: Json
          guru_slug: string | null
          id: string
          reviewed_at: string | null
          reviewed_by: string | null
          reviewer_notes: string | null
          source_video_id: string | null
          source_video_title: string | null
          status: string | null
          submitted_at: string | null
        }
        Insert: {
          entry_json: Json
          guru_slug?: string | null
          id?: string
          reviewed_at?: string | null
          reviewed_by?: string | null
          reviewer_notes?: string | null
          source_video_id?: string | null
          source_video_title?: string | null
          status?: string | null
          submitted_at?: string | null
        }
        Update: {
          entry_json?: Json
          guru_slug?: string | null
          id?: string
          reviewed_at?: string | null
          reviewed_by?: string | null
          reviewer_notes?: string | null
          source_video_id?: string | null
          source_video_title?: string | null
          status?: string | null
          submitted_at?: string | null
        }
        Relationships: []
      }
      pending_extractions: {
        Row: {
          attempts: number
          conversation_id: string | null
          created_at: string | null
          id: string
          last_error: string | null
          message_id: string | null
          payload: Json
          processed_at: string | null
          status: string
          user_id: string
        }
        Insert: {
          attempts?: number
          conversation_id?: string | null
          created_at?: string | null
          id?: string
          last_error?: string | null
          message_id?: string | null
          payload?: Json
          processed_at?: string | null
          status?: string
          user_id: string
        }
        Update: {
          attempts?: number
          conversation_id?: string | null
          created_at?: string | null
          id?: string
          last_error?: string | null
          message_id?: string | null
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
        Relationships: [
          {
            foreignKeyName: "profiles_last_conversation_id_fkey"
            columns: ["last_conversation_id"]
            isOneToOne: false
            referencedRelation: "conversations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "profiles_last_message_id_fkey"
            columns: ["last_message_id"]
            isOneToOne: false
            referencedRelation: "chat_messages"
            referencedColumns: ["id"]
          },
        ]
      }
      prompt_versions: {
        Row: {
          active: boolean | null
          author: string | null
          content: string
          created_at: string | null
          created_by: string | null
          description: string | null
          id: string
          name: string
          version: string
        }
        Insert: {
          active?: boolean | null
          author?: string | null
          content: string
          created_at?: string | null
          created_by?: string | null
          description?: string | null
          id?: string
          name: string
          version: string
        }
        Update: {
          active?: boolean | null
          author?: string | null
          content?: string
          created_at?: string | null
          created_by?: string | null
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
          created_at: string | null
          endpoint: string
          id: string
          p256dh: string
          user_id: string
        }
        Insert: {
          auth: string
          created_at?: string | null
          endpoint: string
          id?: string
          p256dh: string
          user_id: string
        }
        Update: {
          auth?: string
          created_at?: string | null
          endpoint?: string
          id?: string
          p256dh?: string
          user_id?: string
        }
        Relationships: []
      }
      query_clusters: {
        Row: {
          cluster_id: number | null
          cluster_label: string | null
          embedding: Json | null
          query_id: string
        }
        Insert: {
          cluster_id?: number | null
          cluster_label?: string | null
          embedding?: Json | null
          query_id: string
        }
        Update: {
          cluster_id?: number | null
          cluster_label?: string | null
          embedding?: Json | null
          query_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "query_clusters_query_id_fkey"
            columns: ["query_id"]
            isOneToOne: true
            referencedRelation: "chat_queries"
            referencedColumns: ["id"]
          },
        ]
      }
      retention_events: {
        Row: {
          created_at: string
          event: string
          id: number
          props: Json | null
          user_id: string
        }
        Insert: {
          created_at?: string
          event: string
          id?: never
          props?: Json | null
          user_id: string
        }
        Update: {
          created_at?: string
          event?: string
          id?: never
          props?: Json | null
          user_id?: string
        }
        Relationships: []
      }
      retrieval_events: {
        Row: {
          chunk_ids: string[] | null
          id: string
          query_id: string | null
          retrieval_hit: boolean | null
          scores: number[] | null
          source_docs: string[] | null
          tenant_id: string
          top_k: number | null
        }
        Insert: {
          chunk_ids?: string[] | null
          id?: string
          query_id?: string | null
          retrieval_hit?: boolean | null
          scores?: number[] | null
          source_docs?: string[] | null
          tenant_id?: string
          top_k?: number | null
        }
        Update: {
          chunk_ids?: string[] | null
          id?: string
          query_id?: string | null
          retrieval_hit?: boolean | null
          scores?: number[] | null
          source_docs?: string[] | null
          tenant_id?: string
          top_k?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "retrieval_events_query_id_fkey"
            columns: ["query_id"]
            isOneToOne: false
            referencedRelation: "chat_queries"
            referencedColumns: ["id"]
          },
        ]
      }
      router_decisions: {
        Row: {
          confidence: number
          created_at: string
          id: string
          method: string
          query_text: string
          shadow_tier: string | null
          tier: string
        }
        Insert: {
          confidence: number
          created_at?: string
          id: string
          method: string
          query_text: string
          shadow_tier?: string | null
          tier: string
        }
        Update: {
          confidence?: number
          created_at?: string
          id?: string
          method?: string
          query_text?: string
          shadow_tier?: string | null
          tier?: string
        }
        Relationships: []
      }
      safety_events: {
        Row: {
          created_at: string | null
          excerpt: string | null
          id: string
          query_id: string | null
          severity: string | null
          type: string | null
        }
        Insert: {
          created_at?: string | null
          excerpt?: string | null
          id?: string
          query_id?: string | null
          severity?: string | null
          type?: string | null
        }
        Update: {
          created_at?: string | null
          excerpt?: string | null
          id?: string
          query_id?: string | null
          severity?: string | null
          type?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "safety_events_query_id_fkey"
            columns: ["query_id"]
            isOneToOne: false
            referencedRelation: "chat_queries"
            referencedColumns: ["id"]
          },
        ]
      }
      save_offers: {
        Row: {
          accepted: boolean
          applied_at: string | null
          expires_at: string | null
          id: string
          offer_type: string
          user_id: string | null
        }
        Insert: {
          accepted: boolean
          applied_at?: string | null
          expires_at?: string | null
          id?: string
          offer_type: string
          user_id?: string | null
        }
        Update: {
          accepted?: boolean
          applied_at?: string | null
          expires_at?: string | null
          id?: string
          offer_type?: string
          user_id?: string | null
        }
        Relationships: []
      }
      staging_quality_queue: {
        Row: {
          content_hash: string | null
          content_preview: string
          created_at: string
          fail_reasons: string[]
          id: string
          quality_score: number
          reviewed_at: string | null
          reviewed_by: string | null
          reviewer_notes: string
          source_url: string
          status: string
        }
        Insert: {
          content_hash?: string | null
          content_preview: string
          created_at?: string
          fail_reasons: string[]
          id?: string
          quality_score: number
          reviewed_at?: string | null
          reviewed_by?: string | null
          reviewer_notes?: string
          source_url: string
          status?: string
        }
        Update: {
          content_hash?: string | null
          content_preview?: string
          created_at?: string
          fail_reasons?: string[]
          id?: string
          quality_score?: number
          reviewed_at?: string | null
          reviewed_by?: string | null
          reviewer_notes?: string
          source_url?: string
          status?: string
        }
        Relationships: []
      }
      study_notebook_items: {
        Row: {
          answer: string
          citations: Json | null
          created_at: string
          id: string
          notebook_id: string
          query: string
          source_episode_id: string | null
        }
        Insert: {
          answer: string
          citations?: Json | null
          created_at?: string
          id?: string
          notebook_id: string
          query: string
          source_episode_id?: string | null
        }
        Update: {
          answer?: string
          citations?: Json | null
          created_at?: string
          id?: string
          notebook_id?: string
          query?: string
          source_episode_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "study_notebook_items_notebook_id_fkey"
            columns: ["notebook_id"]
            isOneToOne: false
            referencedRelation: "study_notebooks"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "study_notebook_items_source_episode_id_fkey"
            columns: ["source_episode_id"]
            isOneToOne: false
            referencedRelation: "user_episodes"
            referencedColumns: ["id"]
          },
        ]
      }
      study_notebooks: {
        Row: {
          created_at: string
          id: string
          title: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          title: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          title?: string
          user_id?: string
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
      token_usage: {
        Row: {
          cost_usd: number
          created_at: string
          endpoint: string | null
          id: string
          model: string
          provider: string
          session_id: string
          tenant_id: string
          tokens_in: number
          tokens_out: number
          user_id: string
        }
        Insert: {
          cost_usd?: number
          created_at?: string
          endpoint?: string | null
          id?: string
          model?: string
          provider?: string
          session_id?: string
          tenant_id?: string
          tokens_in?: number
          tokens_out?: number
          user_id?: string
        }
        Update: {
          cost_usd?: number
          created_at?: string
          endpoint?: string | null
          id?: string
          model?: string
          provider?: string
          session_id?: string
          tenant_id?: string
          tokens_in?: number
          tokens_out?: number
          user_id?: string
        }
        Relationships: []
      }
      trace_spans: {
        Row: {
          attributes: Json | null
          created_at: string | null
          duration_ms: number | null
          id: string
          name: string
          parent_span_id: string | null
          query_id: string | null
          span_name: string | null
          start_ms: number | null
        }
        Insert: {
          attributes?: Json | null
          created_at?: string | null
          duration_ms?: number | null
          id?: string
          name: string
          parent_span_id?: string | null
          query_id?: string | null
          span_name?: string | null
          start_ms?: number | null
        }
        Update: {
          attributes?: Json | null
          created_at?: string | null
          duration_ms?: number | null
          id?: string
          name?: string
          parent_span_id?: string | null
          query_id?: string | null
          span_name?: string | null
          start_ms?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "trace_spans_parent_span_id_fkey"
            columns: ["parent_span_id"]
            isOneToOne: false
            referencedRelation: "trace_spans"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "trace_spans_query_id_fkey"
            columns: ["query_id"]
            isOneToOne: false
            referencedRelation: "chat_queries"
            referencedColumns: ["id"]
          },
        ]
      }
      trigger_events: {
        Row: {
          created_at: string | null
          id: string
          metadata: Json | null
          query_id: string | null
          trigger_name: string
        }
        Insert: {
          created_at?: string | null
          id?: string
          metadata?: Json | null
          query_id?: string | null
          trigger_name: string
        }
        Update: {
          created_at?: string | null
          id?: string
          metadata?: Json | null
          query_id?: string | null
          trigger_name?: string
        }
        Relationships: [
          {
            foreignKeyName: "trigger_events_query_id_fkey"
            columns: ["query_id"]
            isOneToOne: false
            referencedRelation: "chat_queries"
            referencedColumns: ["id"]
          },
        ]
      }
      user_brain_edges: {
        Row: {
          created_at: string
          dst: string
          id: string
          rel_cipher: string
          src: string
          user_id: string
          weight: number
        }
        Insert: {
          created_at?: string
          dst: string
          id: string
          rel_cipher: string
          src: string
          user_id: string
          weight?: number
        }
        Update: {
          created_at?: string
          dst?: string
          id?: string
          rel_cipher?: string
          src?: string
          user_id?: string
          weight?: number
        }
        Relationships: [
          {
            foreignKeyName: "user_brain_edges_dst_fkey"
            columns: ["dst", "user_id"]
            isOneToOne: false
            referencedRelation: "user_brain_nodes"
            referencedColumns: ["id", "user_id"]
          },
          {
            foreignKeyName: "user_brain_edges_src_fkey"
            columns: ["src", "user_id"]
            isOneToOne: false
            referencedRelation: "user_brain_nodes"
            referencedColumns: ["id", "user_id"]
          },
        ]
      }
      user_brain_keys: {
        Row: {
          created_at: string
          kdf: Json | null
          rotated_at: string | null
          updated_at: string
          user_id: string
          version: number
          wrap_mode: string
          wrapped_dek: string
        }
        Insert: {
          created_at?: string
          kdf?: Json | null
          rotated_at?: string | null
          updated_at?: string
          user_id: string
          version?: number
          wrap_mode?: string
          wrapped_dek: string
        }
        Update: {
          created_at?: string
          kdf?: Json | null
          rotated_at?: string | null
          updated_at?: string
          user_id?: string
          version?: number
          wrap_mode?: string
          wrapped_dek?: string
        }
        Relationships: []
      }
      user_brain_nodes: {
        Row: {
          access_count: number
          blind: string | null
          ciphertext: string
          confidence: number
          created_at: string
          decay: number
          id: string
          kind: string
          updated_at: string
          user_id: string
        }
        Insert: {
          access_count?: number
          blind?: string | null
          ciphertext: string
          confidence?: number
          created_at?: string
          decay?: number
          id: string
          kind: string
          updated_at?: string
          user_id: string
        }
        Update: {
          access_count?: number
          blind?: string | null
          ciphertext?: string
          confidence?: number
          created_at?: string
          decay?: number
          id?: string
          kind?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      user_episodes: {
        Row: {
          answer: string
          citations: Json | null
          created_at: string
          id: string
          intent: string | null
          query: string
          user_id: string
        }
        Insert: {
          answer: string
          citations?: Json | null
          created_at?: string
          id?: string
          intent?: string | null
          query: string
          user_id: string
        }
        Update: {
          answer?: string
          citations?: Json | null
          created_at?: string
          id?: string
          intent?: string | null
          query?: string
          user_id?: string
        }
        Relationships: []
      }
      user_feedback: {
        Row: {
          accuracy: number | null
          comment: string | null
          created_at: string | null
          id: string
          rating: number | null
          response_id: string | null
        }
        Insert: {
          accuracy?: number | null
          comment?: string | null
          created_at?: string | null
          id?: string
          rating?: number | null
          response_id?: string | null
        }
        Update: {
          accuracy?: number | null
          comment?: string | null
          created_at?: string | null
          id?: string
          rating?: number | null
          response_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "user_feedback_response_id_fkey"
            columns: ["response_id"]
            isOneToOne: false
            referencedRelation: "chat_responses"
            referencedColumns: ["id"]
          },
        ]
      }
      user_profiles: {
        Row: {
          codemix_preference: boolean | null
          created_at: number
          favorite_teachings: string[] | null
          last_distress_assessment: Json | null
          preferred_language: string | null
          spiritual_level: string | null
          topics_of_interest: string[] | null
          total_conversations: number | null
          total_meditations_completed: number | null
          updated_at: number
          user_id: string
        }
        Insert: {
          codemix_preference?: boolean | null
          created_at: number
          favorite_teachings?: string[] | null
          last_distress_assessment?: Json | null
          preferred_language?: string | null
          spiritual_level?: string | null
          topics_of_interest?: string[] | null
          total_conversations?: number | null
          total_meditations_completed?: number | null
          updated_at: number
          user_id: string
        }
        Update: {
          codemix_preference?: boolean | null
          created_at?: number
          favorite_teachings?: string[] | null
          last_distress_assessment?: Json | null
          preferred_language?: string | null
          spiritual_level?: string | null
          topics_of_interest?: string[] | null
          total_conversations?: number | null
          total_meditations_completed?: number | null
          updated_at?: number
          user_id?: string
        }
        Relationships: []
      }
      user_retention_cards: {
        Row: {
          answer: string
          created_at: string
          easiness_factor: number
          id: string
          interval_days: number
          next_review_at: string
          question: string
          repetitions: number
          source_id: string | null
          source_type: string
          updated_at: string
          user_id: string
        }
        Insert: {
          answer: string
          created_at?: string
          easiness_factor?: number
          id?: string
          interval_days?: number
          next_review_at?: string
          question: string
          repetitions?: number
          source_id?: string | null
          source_type: string
          updated_at?: string
          user_id: string
        }
        Update: {
          answer?: string
          created_at?: string
          easiness_factor?: number
          id?: string
          interval_days?: number
          next_review_at?: string
          question?: string
          repetitions?: number
          source_id?: string | null
          source_type?: string
          updated_at?: string
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
      user_streaks: {
        Row: {
          current_streak: number
          freezes_available: number
          last_active_date: string | null
          longest_streak: number
          total_practice_days: number
          updated_at: string
          user_id: string
        }
        Insert: {
          current_streak?: number
          freezes_available?: number
          last_active_date?: string | null
          longest_streak?: number
          total_practice_days?: number
          updated_at?: string
          user_id: string
        }
        Update: {
          current_streak?: number
          freezes_available?: number
          last_active_date?: string | null
          longest_streak?: number
          total_practice_days?: number
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      v_chat_queries_by_assistant: {
        Row: {
          assistant_slug: string | null
          avg_completion_tokens: number | null
          avg_latency_ms: number | null
          avg_prompt_tokens: number | null
          last_query_at: string | null
          query_count: number | null
        }
        Relationships: []
      }
      v_meditation_heatmap: {
        Row: {
          day: string | null
          seconds: number | null
          sessions: number | null
          user_id: string | null
        }
        Relationships: []
      }
    }
    Functions: {
      brain_touch: { Args: { p_id: string }; Returns: undefined }
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
      record_practice: {
        Args: { p_practice_date?: string; p_user_id: string }
        Returns: {
          current_streak: number
          freezes_available: number
          last_active_date: string
          longest_streak: number
          milestone_reached: boolean
          total_practice_days: number
        }[]
      }
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
