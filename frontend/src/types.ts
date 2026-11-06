export enum MaterialType {
  book = "book",
  article = "article",
  course = "course",
  lecture = "lecture",
  audiobook = "audiobook"
}

export const MaterialTypes = Object.values(MaterialType);

export function isMaterialType(value: string): value is MaterialType {
  return MaterialTypes.some((materialType) => materialType === value);
}

type GetMaterialItem = {
  material_id: string;
  index: number;
  title: string;
  authors: string;
  pages: number;
  material_type: MaterialType;
  tags: string | null;
  link: string | null;
  added_at: string;
  is_outlined: boolean;
};

type MaterialEstimateJson = {
  material: GetMaterialItem;
  will_be_started: string;
  will_be_completed: string;
  expected_duration: number;
};

/** Fields every cursor-paginated listing response carries. */
export type CursorPageResponse = {
  /** Opaque, `null` when there are no more pages. */
  next_token: string | null;
  total_count: number;
};

export type MinMaxJson = { count: number; date: string };

export type MaterialStatisticsJson = {
  material: GetMaterialItem;
  started_at: string;
  duration: number;
  lost_time: number;
  total: number;
  min_record: MinMaxJson | null;
  max_record: MinMaxJson | null;
  mean: number;
  notes_count: number;
  remaining_pages: number | null;
  remaining_days: number | null;
  /** Present for completed materials list */
  completed_at?: string | null;
  total_reading_duration: string | null;
  would_be_completed: string | null;
  percent_completed: number;
};

type RepeatingQueueJson = {
  material_id: string;
  title: string;
  pages: number;
  material_type: MaterialType;
  is_outlined: boolean;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  completed_at: string | null;
  last_repeated_at: string | null;
  priority_days: number;
  priority_months: number;
};

export type GetRepeatingQueueResponse = CursorPageResponse & {
  repeating_queue: RepeatingQueueJson[];
};


export type MaterialTagsResponse = {
  tags: string[];
};

export type MaterialAuthorsResponse = {
  authors: string[];
}

export type ParsedMaterialResponse = {
  title: string;
  authors: string;
  type: string;
  link: string;
  duration?: number | null;
};

export type ListReadingMaterialsResponse = CursorPageResponse & {
  statistics: MaterialStatisticsJson[];
};

export type ListCompletedMaterialsResponse = CursorPageResponse & {
  statistics: MaterialStatisticsJson[];
};

export type GetCompletedMaterialResponse = {
  statistics: MaterialStatisticsJson;
};

export type ListMaterialsQueueResponse = CursorPageResponse & {
  estimates: MaterialEstimateJson[];
  mean: Record<string, number>;
  /** `start_date` to pass along with `next_token` for the next page. */
  next_start_date: string | null;
};

export type GetMaterialResponse = {
  material: GetMaterialItem;
};

export type GetMaterialCompletionInfoResponse = {
  material_pages: number;
  material_type: MaterialType;
  pages_read: number;
  read_days: number;
}

export type GetMaterialReadingNowResponse = {
  material_id: string;
}

type ListReadingLogsItem = {
  log_id: string;
  material_id: string;
  date: string;
  count: number;
};

export type ListReadingLogsResponse = CursorPageResponse & {
  items: ListReadingLogsItem[];
};

export type ListMaterialsTitlesResponse = {
  items: Record<string, string>;
}

type ListCardsItem = {
  card_id: string;
  note_id: string;
  material_id: string;
  question: string;
  answer: string | null;
  added_at: string;
  note_title: string | null;
  note_content: string;
  note_chapter: string;
  note_page: number;
  material_title: string;
  material_authors: string;
  material_type: MaterialType;
}

export type ListCardsResponse = CursorPageResponse & {
  items: ListCardsItem[];
}

export type SpanSummary = {
  total: number;
  would_be_total: number;
  zero_days: number;
  mean: number;
  median: number;
  max_record: { date: string; amount: number };
  min_record: { date: string; amount: number };
};

type TrackerStatistics = {
  started_at: string;
  finished_at: string;
  duration: number;
  lost_time: number;
  duration_period: string;
  lost_time_period: string;
  lost_time_percent: number;
  mean: number;
  median: number;
  total_materials_completed: number;
  pages_read: Record<string, number>;
  materials_completed: Record<string, number>;
  total_pages_read: number;
  would_be_total: number;
  max_log_record: { count: number; date: string; material_title: string } | null;
  min_log_record: { count: number; date: string; material_title: string } | null;
};

export type SystemSummaryResponse = {
  tracker_statistics: TrackerStatistics;
  reading_trend: SpanSummary;
  notes_trend: SpanSummary;
  completed_materials_trend: SpanSummary;
  repeated_materials_trend: SpanSummary;
  outlined_materials_trend: SpanSummary;
};

export type GraphicResponse = { image: string };

export type BackupResponse = {
  materials_count: number;
  reading_log_count: number;
  statuses_count: number;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  note_repeats_history_count: number;
};

export type RestoreResponse = {
  materials_count: number;
  reading_log_count: number;
  statuses_count: number;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  note_repeats_history_count: number;
};

type Note = {
  note_id: string;
  material_id: string;
  link_id: string | null;
  title: string | null;
  content: string;
  added_at: string;
  chapter: string;
  page: number;
  tags: string[];
  is_deleted: boolean;
  note_number: number;
  links_count: number | null;
}

export type GetNoteResponse = {
  note: Note;
};

export type GetNoteTagsResponse = {
  tags: string[];
};

export type SpellError = {
  word: string;
  suggestions: string[];
};

export type AddNoteRequest = {
  materialId: string;
  title: string;
  content: string;
  tags: string[];
  linkId: string;
  chapter: string;
  page: number;
};

type PossibleLink = {
  note_id: string;
  content: string;
  title?: string;
};

export type ListPossibleLinkResponse = {
  items: PossibleLink[];
}

type NoteLinkItem = {
  note_id: string;
  info: string;
}

export type GetNoteLinksResponse = CursorPageResponse & {
  links_from: NoteLinkItem[];
  link_to: NoteLinkItem;
}